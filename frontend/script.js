const sendBtn = document.getElementById("send-btn");
const messageInput = document.getElementById("message-input");
const chatBox = document.getElementById("chat-box");
const chatForm = document.getElementById("chat-form");
const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const API_BASE_URL = String(window.CHATBOT_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/+$/, "");

function createSessionUserId() {

    if (window.crypto && window.crypto.randomUUID) {
        return `session_${window.crypto.randomUUID()}`;
    }

    return `session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

let userId = createSessionUserId();
let isSending = false;
let initPromise = null;

function addMessage(text, sender) {

    const messageDiv = document.createElement("div");

    messageDiv.classList.add("message");
    messageDiv.classList.add(sender);

    messageDiv.textContent = String(text ?? "");

    chatBox.appendChild(messageDiv);

    chatBox.scrollTop = chatBox.scrollHeight;
}

function setInputEnabled(enabled) {
    messageInput.disabled = !enabled;
    sendBtn.disabled = !enabled;
}

function renderConversation(history) {
    chatBox.innerHTML = "";

    for (const item of history) {
        const sender = item.role === "user" ? "user" : "bot";
        addMessage(item.message, sender);
    }
}

async function loadConversation() {

    const response = await fetch(`${API_BASE_URL}/chat/start/${userId}`);

    if (!response.ok) {
        throw new Error(`Failed to load conversation: ${response.status}`);
    }

    const data = await response.json();
    const history = Array.isArray(data.conversation_history) ? data.conversation_history : [];

    renderConversation(history);
}

async function initializeChat() {
    setInputEnabled(false);

    try {
        await loadConversation();
    } catch (error) {
        console.error(error);
        addMessage("Could not connect to chatbot backend. Check if server is running on port 8000.", "system");
    } finally {
        setInputEnabled(true);
        messageInput.focus();
    }
}

function ensureInitialized() {
    if (!initPromise) {
        initPromise = initializeChat();
    }

    return initPromise;
}

async function sendMessage() {

    if (isSending) return;

    await ensureInitialized();

    const message = messageInput.value.trim();

    if (!message) return;

    isSending = true;
    sendBtn.disabled = true;

    addMessage(message, "user");

    messageInput.value = "";

    try {

        const response = await fetch(`${API_BASE_URL}/chat`, {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                user_id: userId,
                message: message
            })
        });

        if (!response.ok) {
            throw new Error(`Chat request failed: ${response.status}`);
        }

        const data = await response.json();

        if (data.user_id && data.user_id !== userId) {
            userId = data.user_id;
            await loadConversation();
            return;
        }

        addMessage(data.response || "I could not generate a reply right now.", "bot");

    } catch (error) {
        console.error(error);
        addMessage("Request failed. Please check backend logs and retry.", "system");
    } finally {
        isSending = false;
        sendBtn.disabled = false;
        messageInput.focus();
    }
}

chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage();
});

sendBtn.addEventListener("click", (event) => {
    event.preventDefault();
    sendMessage();
});

messageInput.addEventListener("keydown", (event) => {

    const isEnterKey = (
        event.key === "Enter" ||
        event.key === "Return" ||
        event.code === "Enter" ||
        event.code === "NumpadEnter" ||
        event.keyCode === 13
    );

    if (isEnterKey && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        sendMessage();
    }
});

ensureInitialized();
