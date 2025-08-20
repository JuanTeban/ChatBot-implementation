import asyncio
import logging
import time
from typing import Optional, Callable, Any
from functools import wraps

from app.config.settings import (
    ENABLE_RATE_LIMITING,
    MAX_CONCURRENT_LLM_CALLS,
    LLM_REQUEST_DELAY,
    CEREBRAS_RETRY_ATTEMPTS,
    CEREBRAS_RETRY_DELAY
)

logger = logging.getLogger(__name__)

class RateLimiter:
    """Rate limiter para controlar llamadas a APIs externas."""
    
    def __init__(self):
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
        self.last_request_time = 0.0
        self.request_count = 0
    
    async def acquire(self):
        """Adquiere permiso para hacer una request."""
        if not ENABLE_RATE_LIMITING:
            return
        
        # Controlar concurrencia
        await self.semaphore.acquire()
        
        # Controlar velocidad
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < LLM_REQUEST_DELAY:
            sleep_time = LLM_REQUEST_DELAY - time_since_last
            logger.debug(f"⏱️ Rate limiting: esperando {sleep_time:.2f}s")
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
        self.request_count += 1
        logger.debug(f"🚦 Request #{self.request_count} autorizada")
    
    def release(self):
        """Libera el semáforo."""
        if ENABLE_RATE_LIMITING:
            self.semaphore.release()

# Instancia global
_rate_limiter = RateLimiter()

def with_rate_limiting(func: Callable) -> Callable:
    """Decorator para aplicar rate limiting a funciones async que usan LLM."""
    
    @wraps(func)
    async def wrapper(*args, **kwargs):
        await _rate_limiter.acquire()
        try:
            return await func(*args, **kwargs)
        finally:
            _rate_limiter.release()
    
    return wrapper

async def cerebras_request_with_retry(request_func: Callable, *args, **kwargs) -> Any:
    """Ejecuta una request a Cerebras con retry automático."""
    
    for attempt in range(1, CEREBRAS_RETRY_ATTEMPTS + 1):
        try:
            await _rate_limiter.acquire()
            try:
                result = await request_func(*args, **kwargs)
                logger.debug(f"✅ Cerebras request exitosa (intento {attempt})")
                return result
            finally:
                _rate_limiter.release()
                
        except Exception as e:
            error_msg = str(e).lower()
            
            # Verificar si es un error que vale la pena reintentar
            is_retryable = any(keyword in error_msg for keyword in [
                'rate limit', 'timeout', '429', '502', '503', '504'
            ])
            
            if attempt == CEREBRAS_RETRY_ATTEMPTS or not is_retryable:
                logger.error(f"❌ Cerebras request falló definitivamente: {e}")
                raise
            
            # Calcular delay con backoff exponencial
            delay = CEREBRAS_RETRY_DELAY * (2 ** (attempt - 1))
            logger.warning(f"⚠️ Request falló (intento {attempt}), reintentando en {delay}s: {e}")
            await asyncio.sleep(delay)
    
    # Nunca debería llegar aquí, pero por seguridad
    raise RuntimeError("Cerebras request agotó todos los reintentos")