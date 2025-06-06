"""
Módulo principal del bot Sandy
"""
import logging
import asyncio
from typing import Dict, Any
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)

from .config import config
from .gpt_handler import gpt
from .handlers import (
    start_handler,
    callback_handler,
    message_handler,
    document_handler,
    procesar_comparacion,
    iniciar_carga_tracking,
    iniciar_descarga_tracking
)

logger = logging.getLogger(__name__)

class SandyBot:
    """Clase principal del bot"""
    def __init__(self):
        """Inicializa el bot y sus handlers"""
        self.app = Application.builder().token(config.TELEGRAM_TOKEN).build()
        self._setup_handlers()
        
    def _setup_handlers(self):
        """Configura los handlers del bot"""
        # Comandos básicos
        self.app.add_handler(CommandHandler("start", start_handler))
        self.app.add_handler(CommandHandler("procesar", procesar_comparacion))
        self.app.add_handler(CommandHandler("cargar_tracking", iniciar_carga_tracking))
        self.app.add_handler(CommandHandler("descargar_tracking", iniciar_descarga_tracking))
        
        # Callbacks de botones
        self.app.add_handler(CallbackQueryHandler(callback_handler))
        
        # Mensajes de texto
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            message_handler
        ))
        
        # Documentos
        self.app.add_handler(MessageHandler(
            filters.Document.ALL,
            document_handler
        ))
        
        # Error handler
        self.app.add_error_handler(self._error_handler)
        
    async def _error_handler(self, update: Update, context: Any):
        """Maneja errores globales del bot"""
        logger.error("Error procesando update: %s", context.error)
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "😤 Ocurrió un error inesperado. "
                "¿Por qué no intentás más tarde? #NoMeMolestes"
            )
    
    def run(self):
        """Inicia el bot en modo polling"""
        logger.info("🤖 Iniciando SandyBot...")
        self.app.run_polling()
