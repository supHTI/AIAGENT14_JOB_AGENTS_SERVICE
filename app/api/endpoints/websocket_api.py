"""
WebSocket API Endpoints

This module contains WebSocket endpoints for real-time status updates.

Author: [Supriyo Chowdhury]
Version: 1.0
Last Modified: [2024-12-19]
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.cache_db.redis_config import get_redis_client
import json
import logging
import asyncio

logger = logging.getLogger("app_logger")

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/task/{task_id}")
async def websocket_task_status(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint for real-time task status updates using Redis pub/sub.
    
    Args:
        websocket: WebSocket connection
        task_id: Task ID to monitor
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for task: {task_id}")
    
    redis_client = get_redis_client()
    pubsub = None
    
    try:
        # Get initial status from Redis
        initial_status = redis_client.get(f"task_status:{task_id}")
        if initial_status:
            try:
                status_dict = json.loads(initial_status)
                await websocket.send_json(status_dict)
                
                # Auto-disconnect if task is already completed or failed
                if status_dict.get("status") in ["completed", "failed"]:
                    logger.info(f"Task {task_id} already finished, disconnecting WebSocket")
                    await websocket.close()
                    return
            except Exception as e:
                logger.error(f"Error parsing initial status data: {e}")
        
        # Subscribe to Redis pub/sub for real-time updates
        pubsub = redis_client.pubsub()
        channel_name = f"task_status_updates:{task_id}"
        pubsub.subscribe(channel_name)
        logger.info(f"Subscribed to Redis channel: {channel_name}")
        
        # Listen for messages
        while True:
            try:
                # Get message from pub/sub (non-blocking)
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                
                if message:
                    try:
                        # Parse status data
                        if isinstance(message.get('data'), str):
                            status_dict = json.loads(message['data'])
                        elif message.get('data'):
                            status_dict = json.loads(message['data'].decode('utf-8'))
                        else:
                            continue
                        
                        # Send status update to WebSocket client
                        await websocket.send_json(status_dict)
                        logger.debug(f"Sent status update for task {task_id}: {status_dict.get('status')} ({status_dict.get('progress')}%)")
                        
                        # Auto-disconnect if task is completed or failed
                        if status_dict.get("status") in ["completed", "failed"]:
                            logger.info(f"Task {task_id} finished, disconnecting WebSocket")
                            await websocket.close()
                            break
                            
                    except json.JSONDecodeError as e:
                        logger.error(f"Error parsing pub/sub message: {e}")
                    except Exception as e:
                        logger.error(f"Error processing pub/sub message: {e}")
                
                # Also check Redis directly as fallback (in case pub/sub message was missed)
                # Only check periodically to avoid too many Redis calls
                current_status = redis_client.get(f"task_status:{task_id}")
                if current_status:
                    try:
                        status_dict = json.loads(current_status)
                        if status_dict.get("status") in ["completed", "failed"]:
                            await websocket.send_json(status_dict)
                            logger.info(f"Task {task_id} finished (from direct check), disconnecting WebSocket")
                            await websocket.close()
                            break
                    except Exception as e:
                        logger.error(f"Error parsing direct status check: {e}")
                
                # Small sleep to prevent busy waiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in pub/sub message handling: {e}")
                # Continue listening even if there's an error
                await asyncio.sleep(0.5)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task: {task_id}")
    except Exception as e:
        logger.error(f"Error in WebSocket: {e}", exc_info=True)
    finally:
        # Clean up pub/sub subscription
        if pubsub:
            try:
                pubsub.unsubscribe(f"task_status_updates:{task_id}")
                pubsub.close()
            except Exception as e:
                logger.error(f"Error closing pub/sub: {e}")
        try:
            await websocket.close()
        except:
            pass

