
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
from bs4 import BeautifulSoup
import logging
import asyncio
from datetime import datetime

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Variables globales
last_games = []
game_history = []  # Para almacenar historial con timestamps

# Obtener configuración de Secrets
TOKEN = os.environ['TELEGRAM_TOKEN']
CHAT_ID = os.environ.get('CHAT_ID', '')
XBOX_NOW_URL = 'https://www.xbox-now.com/es/game-comparison'

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para obtener el chat ID"""
    chat_id = update.effective_chat.id
    await update.message.reply_text(f'💡 Tu Chat ID es: {chat_id}')

def scrape_xbox_now():
    """Obtiene los juegos de Xbox-Now con nombres y precios"""
    global last_games, game_history
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(XBOX_NOW_URL, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        current_games = []

        # Buscar diferentes selectores posibles para juegos
        game_containers = (
            soup.select('.game-item') or 
            soup.select('.game-card') or 
            soup.select('.product-item') or
            soup.select('.game') or
            soup.find_all('div', class_=lambda x: x and 'game' in x.lower()) or
            soup.find_all('article') or
            soup.find_all('li')
        )

        for container in game_containers[:20]:  # Limitar a 20 elementos para evitar spam
            # Buscar nombre del juego
            game_name = None
            name_selectors = [
                '.game-title', '.title', '.name', '.product-title',
                'h1', 'h2', 'h3', 'h4', '.game-name'
            ]
            
            for selector in name_selectors:
                name_element = container.select_one(selector)
                if name_element:
                    game_name = name_element.text.strip()
                    break
            
            if not game_name:
                # Fallback: usar el texto del contenedor si es corto
                text = container.get_text().strip()
                if len(text) < 100 and len(text.split()) <= 10:
                    game_name = text

            # Buscar precio
            price = None
            price_selectors = [
                '.price', '.cost', '.amount', '.precio', '.value',
                '.price-current', '.price-value', '.game-price'
            ]
            
            for selector in price_selectors:
                price_element = container.select_one(selector)
                if price_element:
                    price_text = price_element.text.strip()
                    # Buscar patrones de precio en pesos argentinos
                    if any(symbol in price_text for symbol in ['$', 'ARS', 'AR$', 'peso']):
                        price = price_text
                        break

            if game_name and len(game_name) > 3:  # Filtrar nombres muy cortos
                game_info = {
                    'name': game_name,
                    'price': price
                }
                current_games.append(game_info)

        # Si no encontramos nada con los selectores específicos, usar método más genérico
        if not current_games:
            all_text_elements = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'span', 'div', 'p'])
            for element in all_text_elements[:30]:
                text = element.text.strip()
                if (len(text) > 5 and len(text) < 80 and 
                    any(keyword in text.lower() for keyword in ['xbox', 'game', 'juego', 'play'])):
                    current_games.append({'name': text, 'price': None})

        if not last_games:
            last_games = current_games
            return None

        # Comparar por nombre de juego
        last_game_names = [game['name'] for game in last_games]
        new_games = [game for game in current_games if game['name'] not in last_game_names]

        if new_games:
            # Agregar timestamp a los juegos nuevos y añadirlos al historial
            current_time = datetime.now()
            for game in new_games:
                game_with_timestamp = {
                    'name': game['name'],
                    'price': game.get('price'),
                    'timestamp': current_time,
                    'date_str': current_time.strftime('%d/%m/%Y'),
                    'time_str': current_time.strftime('%H:%M:%S')
                }
                game_history.append(game_with_timestamp)
            
            # Mantener solo las últimas 50 entradas en el historial
            game_history = game_history[-50:]
            
            last_games = current_games
            return new_games

        return None

    except Exception as e:
        logger.error(f"Error en scraping: {e}")
        return None

async def check_for_updates(context: ContextTypes.DEFAULT_TYPE):
    """Verifica actualizaciones y envía notificaciones"""
    new_games = scrape_xbox_now()
    if new_games and CHAT_ID:
        current_time = datetime.now()
        message_parts = [f"🎮 ¡Nuevos juegos disponibles en Xbox-Now!\n📅 {current_time.strftime('%d/%m/%Y')} - 🕐 {current_time.strftime('%H:%M:%S')}\n"]
        
        for game in new_games:
            if isinstance(game, dict):
                name = game['name']
                price = game.get('price')
                if price:
                    message_parts.append(f"🎯 **{name}**\n💰 Precio: {price}\n")
                else:
                    message_parts.append(f"🎯 **{name}**\n💰 Precio: No disponible\n")
            else:
                message_parts.append(f"🎯 **{game}**\n💰 Precio: No disponible\n")
        
        message = "\n".join(message_parts)
        await context.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start"""
    await update.message.reply_text('🤖 Bot de Xbox-Now iniciado.\n\nComandos disponibles:\n/id - Ver tu Chat ID\n/scan - Escanear manualmente\n/history - Ver últimas 10 publicaciones')

async def manual_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para escanear manualmente"""
    await update.message.reply_text("🔍 Escaneando Xbox-Now...")
    new_games = scrape_xbox_now()
    if new_games:
        current_time = datetime.now()
        message_parts = [f"🎮 Juegos encontrados:\n📅 {current_time.strftime('%d/%m/%Y')} - 🕐 {current_time.strftime('%H:%M:%S')}\n"]
        
        for game in new_games:
            if isinstance(game, dict):
                name = game['name']
                price = game.get('price')
                if price:
                    message_parts.append(f"🎯 **{name}**\n💰 Precio: {price}\n")
                else:
                    message_parts.append(f"🎯 **{name}**\n💰 Precio: No disponible\n")
            else:
                message_parts.append(f"🎯 **{game}**\n💰 Precio: No disponible\n")
        
        message = "\n".join(message_parts)
    else:
        message = "ℹ️ No se encontraron juegos nuevos"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para mostrar las últimas 10 publicaciones con fecha y hora"""
    if not game_history:
        await update.message.reply_text("📝 No hay historial de publicaciones disponible.")
        return
    
    # Obtener las últimas 10 publicaciones
    latest_games = game_history[-10:]
    latest_games.reverse()  # Mostrar las más recientes primero
    
    message_parts = ["📚 **Últimas 10 publicaciones:**\n"]
    
    for i, game in enumerate(latest_games, 1):
        name = game['name']
        price = game.get('price', 'No disponible')
        date_str = game['date_str']
        time_str = game['time_str']
        
        message_parts.append(f"{i}. 🎯 **{name}**")
        message_parts.append(f"   💰 Precio: {price}")
        message_parts.append(f"   📅 Fecha: {date_str}")
        message_parts.append(f"   🕐 Hora: {time_str}\n")
    
    message = "\n".join(message_parts)
    
    # Dividir el mensaje si es muy largo
    if len(message) > 4000:
        # Enviar en partes si es muy largo
        parts = []
        current_part = ["📚 **Últimas 10 publicaciones:**\n"]
        
        for i, game in enumerate(latest_games, 1):
            game_text = [
                f"{i}. 🎯 **{game['name']}**",
                f"   💰 Precio: {game.get('price', 'No disponible')}",
                f"   📅 Fecha: {game['date_str']}",
                f"   🕐 Hora: {game['time_str']}\n"
            ]
            
            test_message = "\n".join(current_part + game_text)
            if len(test_message) > 4000:
                parts.append("\n".join(current_part))
                current_part = game_text
            else:
                current_part.extend(game_text)
        
        if current_part:
            parts.append("\n".join(current_part))
        
        for part in parts:
            await update.message.reply_text(part, parse_mode='Markdown')
    else:
        await update.message.reply_text(message, parse_mode='Markdown')

async def post_init(application: Application):
    """Configura las tareas programadas después de la inicialización"""
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(check_for_updates, interval=3600, first=10)
    else:
        logger.warning("JobQueue no está disponible. Las actualizaciones automáticas no funcionarán.")

def main():
    """Función principal"""
    # Configurar el Application con el JobQueue
    application = Application.builder().token(TOKEN).post_init(post_init).build()

    # Comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("id", get_chat_id))
    application.add_handler(CommandHandler("scan", manual_scan))
    application.add_handler(CommandHandler("history", show_history))

    # Iniciar bot
    logger.info("Bot iniciado...")
    application.run_polling()

if __name__ == '__main__':
    if 'TELEGRAM_TOKEN' not in os.environ:
        logger.error("❌ ERROR: Falta TELEGRAM_TOKEN en Secrets")
    else:
        scrape_xbox_now()  # Scraping inicial
        main()
