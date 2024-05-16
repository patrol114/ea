const express = require('express');
const path = require('path');
const WebSocket = require('ws');
const bodyParser = require('body-parser');
const fs = require('fs');
const crypto = require('crypto');
const dotenv = require('dotenv');
const csvWriter = require('csv-writer').createObjectCsvWriter;
import MistralClient from '@mistralai/mistralai';

// Ładowanie zmiennych środowiskowych
dotenv.config();

const app = express();
app.use(bodyParser.json());
app.use(express.static(path.join(__dirname, 'static')));
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'templates'));

const key = 'yetipatrol114pyy';  // Klucz szyfrowania

// Funkcja do pobierania klucza API
function getApiKey() {
    const apiKey = process.env.MISTRAL_API_KEY;
    if (!apiKey) {
        throw new Error("MISTRAL_API_KEY nie jest ustawiony w zmiennych środowiskowych. Upewnij się, że został ustawiony przed uruchomieniem aplikacji.");
    }
    return apiKey;
}

// Funkcja do tworzenia klienta Mistral
function createMistralClient() {
    const apiKey = getApiKey();
    return new MistralClient(apiKey);
}

// Funkcja do deszyfrowania danych
function decryptData(encryptedData) {
    try {
        const decipher = crypto.createDecipheriv('aes-128-ecb', Buffer.from(key, 'utf-8'), null);
        let decrypted = decipher.update(encryptedData, 'base64', 'utf8');
        decrypted += decipher.final('utf8');
        return JSON.parse(decrypted);
    } catch (e) {
        console.error("Error decrypting data: ", e);
        return null;
    }
}

// Funkcja do tworzenia folderu, jeśli nie istnieje
function createFolderIfNotExists(folderPath) {
    if (!fs.existsSync(folderPath)) {
        fs.mkdirSync(folderPath, { recursive: true });
    }
}

// Funkcja do formatowania daty i czasu
function getFormattedDatetime() {
    const now = new Date();
    return now.toISOString().replace(/T/, ' ').replace(/\..+/, '');
}

// Funkcja do logowania czatu do pliku CSV
function logChatToCsv(userMessage, botMessage) {
    const chatFolder = 'CZATY';
    createFolderIfNotExists(chatFolder);

    const filename = `chat_history-${getFormattedDatetime()}.csv`;
    const filepath = path.join(chatFolder, filename);

    const writer = csvWriter({
        path: filepath,
        header: [
            { id: 'time', title: 'Czas' },
            { id: 'author', title: 'Autor' },
            { id: 'message', title: 'Wiadomość' },
        ]
    });

    const records = [
        { time: getFormattedDatetime(), author: 'Użytkownik', message: userMessage },
        { time: getFormattedDatetime(), author: 'Bot', message: botMessage }
    ];

    writer.writeRecords(records)
        .then(() => console.log('Chat logged successfully.'));
}

// Funkcja do obsługi odpowiedzi czatu
async function getChatResponse(client, userMessage, instructions = {}) {
    try {
        const messages = [{ role: 'user', content: userMessage }];
        if (instructions.language) {
            messages.push({ role: 'system', content: instructions.language });
        }
        if (instructions.name) {
            messages.push({ role: 'system', content: instructions.name });
        }
        if (instructions.ai) {
            messages.push({ role: 'system', content: instructions.ai });
        }

        const chatStreamResponse = await client.chatStream({
            model: 'mistral-tiny',
            messages
        });

        let responseContent = '';
        for await (const chunk of chatStreamResponse) {
            if (chunk.choices[0].delta.content !== undefined) {
                responseContent += chunk.choices[0].delta.content;
            }
        }

        return responseContent;
    } catch (e) {
        return e.message;
    }
}

// Konfiguracja serwera WebSocket
const wss = new WebSocket.Server({ noServer: true });

wss.on('connection', ws => {
    ws.on('message', async message => {
        const data = decryptData(message);
        if (data) {
            const client = createMistralClient();
            const response = await getChatResponse(client, data.message, data.instructions);
            ws.send(response);
        } else {
            ws.send('Błąd deszyfrowania wiadomości.');
        }
    });
});

// Konfiguracja serwera HTTP
app.get('/', (req, res) => {
    res.render('chat');
});

const server = app.listen(8080, () => {
    console.log('Server running on port 8080');
});

// Konfiguracja przekierowania HTTP na HTTPS
const redirectDomain = process.env.REDIRECT_DOMAIN || 'yetiai.pl';
const redirectTarget = process.env.REDIRECT_TARGET || 'https://cheaply-enormous-bunny.ngrok-free.app';

app.get('*', (req, res) => {
    res.redirect(redirectTarget + req.originalUrl);
});

// Obsługa serwera WebSocket w ramach serwera HTTP
server.on('upgrade', (request, socket, head) => {
    wss.handleUpgrade(request, socket, head, ws => {
        wss.emit('connection', ws, request);
    });
});
