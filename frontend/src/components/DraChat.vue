<template>
  <div class="ds-container fade-in">
    <header class="ds-header">
      <div class="model-select-wrapper">
        <span class="ds-icon">🚀</span>
        <span style="color:#e2e8f0; font-weight:600; margin-right: 10px;">选择靶机:</span>
        <select v-model="selectedModel" class="ds-select">
          <option value="ollama-deepseek-r1:latest">DeepSeek-R1 (14b)</option>
          <option value="ollama-qwen2:7b">Qwen-2 (7b)</option>
          <option value="ollama-llama3:8b">Llama-3 (8b)</option>
        </select>
      </div>
      <div class="header-title">DRA 越狱纯净沙箱 (流式输出)</div>
    </header>

    <div class="workbench-layout">
      <div class="workbench-section input-section">
        <div class="section-header">
          <span><span class="status-dot"></span> 攻击负载输入区 (Attacker Payload)</span>
          <button class="ds-send-btn" @click="sendChatMessage" :disabled="isChatting || !chatInput.trim()">
            <span v-if="isChatting" class="loader"></span>
            <span v-else>▶ 执行注入</span>
          </button>
        </div>
        <textarea 
          v-model="chatInput" 
          class="payload-editor"
          placeholder="在此粘贴由 Debug 页面生成的复杂越狱 Prompt..."
          :disabled="isChatting"
        ></textarea>
      </div>

      <div class="divider">
        <span class="divider-text">TARGET RESPONSE</span>
      </div>

      <div class="workbench-section output-section">
        <div class="section-header" style="background-color: #3f181d; border-bottom: 1px solid #7f1d1d;">
          <span style="color:#fca5a5;"><span class="status-dot red"></span> 靶机大模型响应区 (Streaming Output)</span>
        </div>
        <div class="response-terminal" ref="chatTerminalRef">
          
          <div v-if="!currentResponse && !isChatting" class="empty-terminal">
            SYSTEM STANDBY. 等待执行攻击负载...
          </div>
          
          <div v-else-if="!currentResponse && isChatting" class="empty-terminal" style="color: #38bdf8;">
            <span class="loader" style="display:inline-block; border-color:#38bdf8; border-top-color:transparent; margin-right: 10px;"></span> 
            连接已建立，等待大模型吐出首字...
          </div>

          <div v-else class="response-content">
            <div class="markdown-body" v-html="formatMessage(currentResponse)"></div>
            <span v-if="isChatting" class="cursor-blink">▍</span>
          </div>

        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const selectedModel = ref('ollama-deepseek-r1:latest')
const chatInput = ref("")
const currentResponse = ref("")
const isChatting = ref(false)
const chatTerminalRef = ref(null)

// 动态处理文本：将换行符替换为 <br>，并将 <think> 标签转化为高亮的思考框！
const formatMessage = (text) => {
  if (!text) return ''
  let formatted = text.replace(/<think>/g, '<div class="think-box">💡 <b>模型的内心活动 (Reasoning)：</b><br/><br/>');
  formatted = formatted.replace(/<\/think>/g, '</div>');
  formatted = formatted.replace(/\n/g, '<br/>');
  return formatted;
}

// 核心流式请求逻辑
const sendChatMessage = async () => {
  if (!chatInput.value.trim() || isChatting.value) return;
  
  const userText = chatInput.value.trim();
  isChatting.value = true;
  currentResponse.value = ""; // 清空上一次结果
  
  try {
    // 请求新增的流式接口
    const response = await fetch('/api/dra/chat_stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: userText, model: selectedModel.value })
    });

    if (!response.ok) throw new Error(`HTTP 错误! 状态码: ${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data:')) {
          try {
            const data = JSON.parse(line.substring(5).trim());
            if (data.text) {
              currentResponse.value += data.text;
              scrollToBottomChat(); // 每次拼接新字后滚动到底部
            }
          } catch (e) {
            // 忽略因流被截断导致的 JSON 解析错误
          }
        }
      }
    }
  } catch (err) {
    currentResponse.value += `<br/><br/><span style="color:#ef4444;">[网络中断或请求失败]: ${err.message}</span>`;
  } finally {
    isChatting.value = false;
  }
}

const scrollToBottomChat = () => {
  nextTick(() => {
    if (chatTerminalRef.value) {
      chatTerminalRef.value.scrollTop = chatTerminalRef.value.scrollHeight;
    }
  });
}
</script>

<style scoped>
/* 容器基础样式 */
.ds-container { display: flex; flex-direction: column; height: 100%; background-color: #0b0f19; border-radius: 8px; border: 1px solid #1e293b; overflow: hidden; color: #e2e8f0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;}
.ds-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; background-color: #111827; border-bottom: 1px solid #1e293b;}
.ds-select { background: #1e293b; color: #38bdf8; border: 1px solid #334155; padding: 6px 12px; border-radius: 4px; outline: none; font-size: 0.9rem; cursor: pointer; font-weight: 600;}
.header-title { color: #64748b; font-size: 0.85rem; font-weight: bold; letter-spacing: 1px;}
.workbench-layout { flex: 1; display: flex; flex-direction: column; overflow: hidden;}
.workbench-section { display: flex; flex-direction: column; overflow: hidden;}
.input-section { flex: 0 0 45%; background: #0f172a;}
.output-section { flex: 1; background: #05070a;}
.section-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 15px; background-color: #1e293b; font-size: 0.9rem; font-weight: bold; color: #cbd5e1; border-bottom: 1px solid #334155;}
.status-dot { display: inline-block; width: 8px; height: 8px; background-color: #3b82f6; border-radius: 50%; margin-right: 8px; box-shadow: 0 0 8px #3b82f6;}
.status-dot.red { background-color: #ef4444; box-shadow: 0 0 8px #ef4444;}
.payload-editor { flex: 1; width: 100%; box-sizing: border-box; background: transparent; border: none; color: #38bdf8; font-family: 'Courier New', Courier, monospace; font-size: 0.95rem; line-height: 1.5; padding: 15px; resize: none; outline: none; white-space: pre-wrap; word-break: break-all; overflow-y: auto;}
.divider { height: 20px; background: #0b0f19; border-top: 1px solid #1e293b; border-bottom: 1px solid #1e293b; display: flex; align-items: center; justify-content: center;}
.divider-text { font-size: 0.7rem; color: #475569; letter-spacing: 2px; font-weight: bold;}
.response-terminal { flex: 1; padding: 20px; overflow-y: auto; font-family: 'Courier New', Courier, monospace;}
.empty-terminal { color: #475569; text-align: center; margin-top: 50px; font-size: 0.9rem;}
.response-content { color: #fca5a5; line-height: 1.6; font-size: 0.95rem; word-wrap: break-word;}

/* 👇 针对 DeepSeek 的思考过程进行视觉美化 */
:deep(.think-box) {
  margin: 10px 0 20px 0;
  padding: 15px;
  background-color: rgba(255, 255, 255, 0.03);
  border-left: 4px solid #64748b;
  color: #94a3b8;
  font-style: italic;
  border-radius: 4px;
}

.ds-send-btn { background-color: #2563eb; color: white; border: none; border-radius: 4px; padding: 6px 15px; cursor: pointer; font-weight: bold; transition: 0.2s; font-size: 0.85rem; display: flex; align-items: center; justify-content: center;}
.ds-send-btn:disabled { background-color: #475569; color: #94a3b8; cursor: not-allowed; }
.ds-send-btn:hover:not(:disabled) { background-color: #1d4ed8; }
textarea::-webkit-scrollbar, .response-terminal::-webkit-scrollbar { width: 6px; }
textarea::-webkit-scrollbar-thumb, .response-terminal::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
.loader { border: 2px solid #94a3b8; border-top: 2px solid #fff; border-radius: 50%; width: 14px; height: 14px; animation: spin 1s linear infinite; }

/* 闪烁的光标效果 */
.cursor-blink { font-weight: bold; color: #fca5a5; animation: blink 1s step-end infinite; }
@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
@keyframes blink { 50% { opacity: 0; } }
</style>