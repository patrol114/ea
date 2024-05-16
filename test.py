from aiohttp import web
import aiohttp_jinja2
import jinja2
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
import os
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64
import json
import csv
from datetime import datetime
from asyncio import sleep
import time
client = None  # Globalny klient
key = b'yetipatrol114pyy'  # Klucz jako bajty

def get_api_key():
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise ValueError("API_KEY nie jest ustawiony w zmiennych środowiskowych. Upewnij się, że został ustawiony przed uruchomieniem aplikacji.")
    return api_key

def create_mistral_client():
    global client
    if client is None:
        api_key = get_api_key()
        client = MistralClient(api_key=api_key)
    return client

@aiohttp_jinja2.template('chat.html')
async def index(request):
    return {}

def decrypt_data(encrypted_data):
    try:
        cipher = AES.new(key, AES.MODE_ECB)
        decrypted = unpad(cipher.decrypt(base64.b64decode(encrypted_data)), AES.block_size)
        return json.loads(decrypted.decode('utf-8'))
    except Exception as e:
        print(f"Error decrypting data: {e}")
        return None

def create_folder_if_not_exists(folder_path):
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

def get_formatted_datetime():
    now = datetime.now()
    return now.strftime('%d-%m-%Y_%H-%M-%S')

def log_chat_to_csv(user_message, bot_message):
    chat_folder = 'CZATY'
    create_folder_if_not_exists(chat_folder)

    filename = f'chat_history-{get_formatted_datetime()}.csv'
    filepath = os.path.join(chat_folder, filename)

    with open(filepath, 'a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)

        if os.stat(filepath).st_size == 0:
            writer.writerow(["Czas", "Autor", "Wiadomość"])

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        writer.writerow([now, "Użytkownik", user_message])
        writer.writerow([now, "Bot", bot_message])

async def async_generator(stream_response):
    for chunk in stream_response:
        await sleep(0)  # Allow other tasks to run
        yield chunk

async def stream_chat_response(client, user_message, instructions=None):
    messages = [ChatMessage(role="user", content=user_message)]
    if instructions:
        for key in ['language', 'name', 'ai']:
            if key in instructions:
                messages.append(ChatMessage(role="system", content=instructions[key]))

    # Upewnij się, że ostatnia wiadomość ma rolę 'user'
    if messages[-1].role != "user":
        messages.append(ChatMessage(role="user", content=user_message))

    # Konwersja wiadomości na słowniki (jeśli to konieczne)
    parsed_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

    stream_response = client.chat_stream(model="mistral-large-latest", messages=parsed_messages)
    async for chunk in async_generator(stream_response):
        yield chunk.choices[0].delta.content

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    mistral_client = create_mistral_client()

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            encrypted_data = msg.data
            decrypted_data = decrypt_data(encrypted_data)
            if decrypted_data:
                user_message = decrypted_data.get("message")
                instructions = decrypted_data.get("instructions")

                # Przesyłanie wiadomości użytkownika do frontendu
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                user_message_data = {"time": now, "message": user_message, "sender": "user"}
                await ws.send_json(user_message_data)

                # Przetwarzanie i wysyłanie odpowiedzi modelu
                bot_message_id = int(time.time() * 1000)  # Unique ID for the bot message div
                full_response = []
                async for response_chunk in stream_chat_response(mistral_client, user_message, instructions):
                    full_response.append(response_chunk)
                    await ws.send_json({"message": response_chunk, "is_partial": True, "sender": "bot", "id": bot_message_id})

                # Logowanie pełnej odpowiedzi modelu
                full_response_str = ''.join(full_response)
                log_chat_to_csv(user_message, full_response_str)

        elif msg.type == web.WSMsgType.ERROR:
            print(f'WebSocket connection closed with exception {ws.exception()}')

    print('WebSocket connection closed')
    return ws

async def create_app():
    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('templates'))
    app.router.add_get('/', index)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_static('/static/', path='static', name='static')

    redirect_domain = os.getenv('REDIRECT_DOMAIN', 'yetiai.pl')
    redirect_target = os.getenv('REDIRECT_TARGET', 'yetiai.pl')

    async def redirect_handler(request):
        raise web.HTTPMovedPermanently(redirect_target + request.rel_url.path_qs)

    app.router.add_get('/{_:.*}', redirect_handler, name='redirect')

    return app

if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="localhost", port=80)
