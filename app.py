from flask import Flask, request, jsonify
import requests
from gtts import gTTS
import tempfile
import os
import base64
import io
import threading
import json
from datetime import datetime

app = Flask(__name__)

# API konfigürasyonu
API_KEY = "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"
MODEL = "mistralai/mistral-7b-instruct"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "http://localhost",
    "X-Title": "Elise"
}


# Hafıza dosyası ve şifre
MEMORY_FILE = "user_memory.json"
PRIMARY_PASSWORD = "cetin2357"

class MemoryManager:
    def __init__(self, enabled=True):
        self.memory_file = MEMORY_FILE
        self.enabled = enabled
        if self.enabled:
            self.load_memory()
    
    def load_memory(self):
        """Hafızayı dosyadan yükle"""
        if not self.enabled:
            return self.create_default_memory()
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                base_memory = self.create_default_memory()
                self.save_memory(base_memory)
                return base_memory
        except:
            return self.create_default_memory()
    
    def create_default_memory(self):
        """Varsayılan hafıza oluştur"""
        return {
            "user_info": {
                "name": "User",
                "age": None,
                "location": None,
                "interests": [],
                "preferences": {},
                "conversation_history": []
            },
            "last_updated": datetime.now().isoformat()
        }
    
    def save_memory(self, memory_data):
        """Hafızayı dosyaya kaydet"""
        if not self.enabled:
            return False
        try:
            memory_data["last_updated"] = datetime.now().isoformat()
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=2)
            return True
        except:
            return False
    
    def extract_user_info(self, message, response):
        """Mesajdan kullanıcı bilgilerini çıkar ve kaydet"""
        memory = self.load_memory()
        
        # İsim tespiti
        name_keywords = ["adım", "ismim", "benim adım", "name is", "my name is", "I'm", "I am"]
        for keyword in name_keywords:
            if keyword in message.lower():
                if keyword in ["adım", "ismim", "benim adım"]:
                    parts = message.lower().split(keyword)
                    if len(parts) > 1:
                        name = parts[1].strip().split()[0].title()
                        memory["user_info"]["name"] = name
                elif keyword in ["name is", "my name is", "I'm", "I am"]:
                    parts = message.lower().split(keyword)
                    if len(parts) > 1:
                        name = parts[1].strip().split()[0].title()
                        memory["user_info"]["name"] = name
        
        # Yaş tespiti
        age_keywords = ["yaşım", "I am", "I'm", "years old", "yaşındayım"]
        for keyword in age_keywords:
            if keyword in message.lower():
                import re
                age_match = re.search(r'\b(\d{1,2})\b', message)
                if age_match:
                    memory["user_info"]["age"] = age_match.group(1)
        
        # Konum tespiti
        location_keywords = ["yaşıyorum", "live in", "from", "şehir", "city", "ülke", "country"]
        for keyword in location_keywords:
            if keyword in message.lower():
                # Basit bir konum çıkarımı
                parts = message.lower().split(keyword)
                if len(parts) > 1:
                    location = parts[1].strip().split('.')[0].split('?')[0].title()
                    memory["user_info"]["location"] = location
        
        # Konuşma geçmişine ekle
        memory["user_info"]["conversation_history"].append({
            "timestamp": datetime.now().isoformat(),
            "user_message": message,
            "ai_response": response
        })
        
        # Son 20 mesajı tut (eski mesajları temizle)
        if len(memory["user_info"]["conversation_history"]) > 20:
            memory["user_info"]["conversation_history"] = memory["user_info"]["conversation_history"][-20:]
        
        self.save_memory(memory)
        return memory

class EliseAI:
    def __init__(self, memory_enabled=True):
        self.memory_manager = MemoryManager(enabled=memory_enabled)
    
    def get_ai_response(self, message):
        """AI'dan yanıt al"""
        memory = self.memory_manager.load_memory()
        system_prompt = self._create_personalized_prompt(memory)
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            "temperature": 0.7,
            "max_tokens": 300
        }
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            ai_response = result['choices'][0]['message']['content']
            # Sadece birincil kullanıcı için hafıza kaydı
            if self.memory_manager.enabled:
                self.memory_manager.extract_user_info(message, ai_response)
            return ai_response
        except Exception as e:
            return f"Sorry, an error occurred: {str(e)}"
    
    def _create_personalized_prompt(self, memory):
        """Kişiselleştirilmiş sistem prompt'u oluştur"""
        user_info = memory["user_info"]
        
        prompt = f"""You are Elise, a friendly AI assistant. You have memory of past conversations.

User information you know:
- Name: {user_info['name']}
- Age: {user_info['age'] or 'Unknown'}
- Location: {user_info['location'] or 'Unknown'}
- Interests: {', '.join(user_info['interests']) if user_info['interests'] else 'None yet'}

Recent conversation history:
"""
        
        # Son 5 konuşmayı prompt'a ekle
        for i, conv in enumerate(user_info['conversation_history'][-5:]):
            prompt += f"- User: {conv['user_message']}\n"
            prompt += f"- You: {conv['ai_response']}\n"
        
        prompt += """
Instructions:
1. Be friendly, helpful and conversational
2. Use the user's name when appropriate
3. Remember details from previous conversations
4. Keep responses concise but engaging
5. If user shares new personal information, remember it naturally
6. Speak in English but understand Turkish
"""
        
        return prompt

    def text_to_speech(self, text):
        """Metni sese çevir ve base64 olarak döndür"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # İngilizce seslendirme
                tts = gTTS(text=text, lang='en', slow=False)
                
                # Memory'de tut
                audio_buffer = io.BytesIO()
                tts.write_to_fp(audio_buffer)
                audio_buffer.seek(0)
                
                # Base64'e çevir
                audio_data = base64.b64encode(audio_buffer.getvalue()).decode('utf-8')
                return audio_data
                
            except Exception as e:
                retry_count += 1
                print(f"Ses hatası (deneme {retry_count}): {e}")
                if retry_count == max_retries:
                    return None
                # 1 saniye bekle ve tekrar dene
                threading.Event().wait(1)


# HTML içeriği (giriş ve chat ekranı bir arada, tek dosya)
HTML_CONTENT = """
<!DOCTYPE html>
<html lang='tr'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>Elise - AI Assistant</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; display: flex; justify-content: center; align-items: center; }
        .container { width: 100%; max-width: 800px; background: white; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); overflow: hidden; display: flex; flex-direction: column; height: 90vh; }
        .header { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; padding: 20px; text-align: center; flex-shrink: 0; }
        .header h1 { font-size: 2em; margin-bottom: 5px; font-weight: 300; }
        .header p { font-size: 1em; opacity: 0.9; }
        .chat-container { flex: 1; overflow-y: auto; padding: 20px; background: #f8f9fa; display: flex; flex-direction: column; }
        .message { margin-bottom: 15px; display: flex; }
        .user-message { justify-content: flex-end; }
        .ai-message { justify-content: flex-start; }
        .message-content { max-width: 80%; padding: 12px 16px; border-radius: 18px; word-wrap: break-word; line-height: 1.4; }
        .user-message .message-content { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; border-bottom-right-radius: 5px; }
        .ai-message .message-content { background: white; color: #333; border: 1px solid #e0e0e0; border-bottom-left-radius: 5px; }
        .typing-animation { display: inline-block; overflow: hidden; border-right: 2px solid #4facfe; white-space: pre-wrap; animation: typing 0.5s steps(40, end), blink-caret 0.75s step-end infinite; }
        @keyframes typing { from { width: 0; } to { width: 100%; } }
        @keyframes blink-caret { from, to { border-color: transparent; } 50% { border-color: #4facfe; } }
        .input-container { padding: 15px; background: white; border-top: 1px solid #e0e0e0; display: flex; gap: 10px; flex-shrink: 0; }
        #message-input { flex: 1; padding: 12px; border: 2px solid #e0e0e0; border-radius: 25px; outline: none; font-size: 14px; transition: border-color 0.3s; }
        #message-input:focus { border-color: #4facfe; }
        #send-button { padding: 12px 20px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; border: none; border-radius: 25px; cursor: pointer; font-size: 14px; transition: transform 0.2s; }
        #send-button:hover { transform: translateY(-1px); }
        #send-button:disabled { opacity: 0.6; cursor: not-allowed; }
        .audio-button { background: #4facfe; color: white; border: none; padding: 8px 15px; border-radius: 15px; cursor: pointer; font-size: 12px; margin-top: 8px; transition: background 0.2s; display: flex; align-items: center; gap: 5px; }
        .audio-button:hover { background: #3ba1fe; }
        .message-time { font-size: 11px; color: #888; margin-top: 5px; text-align: right; }
        .loading-spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #f3f3f3; border-top: 2px solid #4facfe; border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .chat-container::-webkit-scrollbar { width: 6px; }
        .chat-container::-webkit-scrollbar-track { background: #f1f1f1; }
        .chat-container::-webkit-scrollbar-thumb { background: #c1c1c1; border-radius: 3px; }
        .chat-container::-webkit-scrollbar-thumb:hover { background: #a8a8a8; }
        #login-screen { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 70vh; }
        #password-area { display: none; flex-direction: column; align-items: center; }
        #password-input { padding: 10px; border-radius: 10px; border: 1px solid #ccc; margin-bottom: 10px; }
        #login-btn { padding: 8px 20px; border-radius: 10px; background: #4facfe; color: white; border: none; cursor: pointer; }
        #login-error { color: red; margin-top: 8px; display: none; }
        #primary-user-btn { padding: 12px 30px; font-size: 1.1em; border-radius: 20px; background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; border: none; margin-bottom: 20px; cursor: pointer; }
        #guest-btn { padding: 10px 25px; font-size: 1em; border-radius: 20px; background: #e0e0e0; color: #333; border: none; cursor: pointer; }
        #chat-area { display: none; flex-direction: column; height: 100%; }
    </style>
</head>
<body>
    <div class='container'>
        <div class='header'>
            <h1>Elise</h1>
            <p>AI Assistant with Memory</p>
        </div>
        <!-- Giriş ekranı -->
        <div id='login-screen'>
            <button id='primary-user-btn'>Birincil Kullanıcı</button>
            <div id='password-area'>
                <input type='password' id='password-input' placeholder='Şifre'>
                <button id='login-btn'>Giriş Yap</button>
                <div id='login-error'></div>
            </div>
            <button id='guest-btn'>Misafir Olarak Devam Et</button>
        </div>
        <!-- Sohbet ekranı -->
        <div id='chat-area'>
            <div class='chat-container' id='chat-container'>
                <div class='message ai-message'>
                    <div class='message-content'>
                        Hello! I'm Elise. How can I help you today?
                        <div class='message-time'>just now</div>
                    </div>
                </div>
            </div>
            <div class='input-container'>
                <input type='text' id='message-input' placeholder='Type your message here...' autocomplete='off'>
                <button id='send-button'>Send</button>
            </div>
        </div>
    </div>
    <script>
        // Giriş ve sohbet alanları
        const loginScreen = document.getElementById('login-screen');
        const passwordArea = document.getElementById('password-area');
        const passwordInput = document.getElementById('password-input');
        const loginBtn = document.getElementById('login-btn');
        const loginError = document.getElementById('login-error');
        const primaryUserBtn = document.getElementById('primary-user-btn');
        const guestBtn = document.getElementById('guest-btn');
        const chatArea = document.getElementById('chat-area');
        const chatContainer = document.getElementById('chat-container');
        const messageInput = document.getElementById('message-input');
        const sendButton = document.getElementById('send-button');
        let isProcessing = false;
        let isPrimary = false;

        // Giriş ekranı eventleri
        primaryUserBtn.onclick = () => {
            passwordArea.style.display = 'flex';
            passwordInput.focus();
        };
        loginBtn.onclick = () => {
            const password = passwordInput.value;
            fetch('/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    isPrimary = true;
                    loginScreen.style.display = 'none';
                    chatArea.style.display = 'flex';
                    messageInput.focus();
                } else {
                    loginError.textContent = 'Şifre yanlış!';
                    loginError.style.display = 'block';
                }
            });
        };
        passwordInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') loginBtn.onclick();
        });
        guestBtn.onclick = () => {
            isPrimary = false;
            loginScreen.style.display = 'none';
            chatArea.style.display = 'flex';
            messageInput.focus();
        };

        function formatTime(date = new Date()) {
            return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        }
        function addMessage(text, isUser = false) {
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message ' + (isUser ? 'user-message' : 'ai-message');
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            if (isUser) {
                contentDiv.textContent = text;
            } else {
                contentDiv.innerHTML = '<div class="typing-animation">' + text + '</div>';
            }
            const timeDiv = document.createElement('div');
            timeDiv.className = 'message-time';
            timeDiv.textContent = formatTime();
            contentDiv.appendChild(timeDiv);
            messageDiv.appendChild(contentDiv);
            chatContainer.appendChild(messageDiv);
            setTimeout(() => { chatContainer.scrollTop = chatContainer.scrollHeight; }, 100);
            return contentDiv;
        }
        function updateMessage(element, newText) {
            element.innerHTML = '<div class="typing-animation">' + newText + '</div>' + '<div class="message-time">' + formatTime() + '</div>';
        }
        async function sendMessage() {
            if (isProcessing) return;
            const message = messageInput.value.trim();
            if (!message) return;
            isProcessing = true;
            sendButton.disabled = true;
            messageInput.disabled = true;
            sendButton.textContent = 'Sending...';
            addMessage(message, true);
            messageInput.value = '';
            const aiMessageElement = addMessage('Thinking...', false);
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message, is_primary: isPrimary })
                });
                const data = await response.json();
                if (response.ok) {
                    let displayedText = '';
                    for (let i = 0; i < data.response.length; i++) {
                        displayedText += data.response[i];
                        updateMessage(aiMessageElement, displayedText);
                        await new Promise(resolve => setTimeout(resolve, 20));
                    }
                    const audioButton = document.createElement('button');
                    audioButton.className = 'audio-button';
                    audioButton.innerHTML = '🔊 Play Voice';
                    audioButton.onclick = () => speakText(data.response);
                    aiMessageElement.appendChild(audioButton);
                } else {
                    updateMessage(aiMessageElement, 'Error: ' + data.error);
                }
            } catch (error) {
                updateMessage(aiMessageElement, 'Connection error');
            } finally {
                isProcessing = false;
                sendButton.disabled = false;
                messageInput.disabled = false;
                sendButton.textContent = 'Send';
                messageInput.focus();
            }
        }
        async function speakText(text) {
            try {
                const audioButton = event.target;
                const originalText = audioButton.innerHTML;
                audioButton.innerHTML = '<div class="loading-spinner"></div>';
                audioButton.disabled = true;
                const response = await fetch('/speak', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: text, is_primary: isPrimary })
                });
                const data = await response.json();
                if (response.ok && data.audio_data) {
                    const audio = new Audio('data:audio/mp3;base64,' + data.audio_data);
                    audio.play();
                    audio.onended = () => {
                        audioButton.innerHTML = '🔊 Play Voice';
                        audioButton.disabled = false;
                    };
                } else {
                    throw new Error(data.error || 'Voice generation failed');
                }
            } catch (error) {
                console.error('Voice error:', error);
                event.target.innerHTML = '🔊 Play Voice';
                event.target.disabled = false;
                alert('Voice playback failed. Please try again.');
            }
        }
        sendButton.addEventListener('click', sendMessage);
        messageInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
        chatArea.style.display = 'none';
        loginScreen.style.display = 'flex';
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return HTML_CONTENT

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_message = request.json.get('message')
        is_primary = request.json.get('is_primary', False)
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        ai = EliseAI(memory_enabled=bool(is_primary))
        response = ai.get_ai_response(user_message)
        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/speak', methods=['POST'])
def speak():
    try:
        text = request.json.get('text')
        is_primary = request.json.get('is_primary', False)
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        ai = EliseAI(memory_enabled=bool(is_primary))
        audio_data = ai.text_to_speech(text)
        if audio_data:
            return jsonify({'audio_data': audio_data})
        else:
            return jsonify({'error': 'Speech generation failed after retries'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Şifre kontrol endpoint'i
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    password = data.get('password', '')
    if password == PRIMARY_PASSWORD:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False}), 401

if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)