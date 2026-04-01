<template>
  <div class="page-grid fade-in">
    <div class="panel config-panel">
      <h3 class="panel-header">自动化越狱攻击</h3>
      
      <div class="form-group">
        <label>目标靶机 Target Model</label>
        <select v-model="targetModel" class="cyber-input">
          <option value="ollama-deepseek-r1:latest">DeepSeek-R1 (14b)</option>
          <option value="ollama-qwen2:7b">Qwen-2 (7b)</option>
          <option value="ollama-llama3:8b">Llama-3 (8b)</option>
        </select>
      </div>

      <div class="form-group" style="margin-top: 20px; flex: 1; display:flex; flex-direction:column; overflow:hidden;">
        <label>测试集 (Behaviors)</label>
        <div style="flex:1; overflow-y: auto; background: #05070a; border: 1px solid #334155; border-radius: 4px; padding: 10px;">
          <ul style="list-style: none; padding: 0; margin: 0;">
            <li v-for="(item, index) in behaviors" :key="index" 
                @click="selectBehavior(item)"
                :style="{
                  padding: '8px', borderBottom: '1px solid #1e293b', cursor: 'pointer',
                  color: currentQuery === item ? '#38bdf8' : '#94a3b8',
                  background: currentQuery === item ? '#1e293b' : 'transparent'
                }">
              {{ index + 1 }}. {{ item }}
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div class="panel terminal-panel" style="display:flex; flex-direction:column;">
      <h3 class="panel-header">攻击监控台</h3>
      
      <div style="display:flex; gap:10px; margin-bottom: 20px;">
        <input v-model="currentQuery" readonly class="cyber-input" style="flex:1;" placeholder="👈 请从左侧选择一条恶意指令..." />
        <button class="action-btn danger-btn" style="width: 150px; margin-top:0;" @click="runAttack" :disabled="!currentQuery || loading">
          {{ loading ? '攻击执行中...' : '发起单点攻击' }}
        </button>
      </div>

      <div v-if="attackResult" class="data-card" style="margin: 0; flex:1; display:flex; flex-direction:column;">
        <div class="card-title">
          <span>攻击结果 (Attack Result)</span>
          <span :class="['badge', attackResult.is_jailbroken ? 'badge-danger' : 'badge-safe']">
            {{ attackResult.is_jailbroken ? '🛑 越狱成功 (Jailbroken)' : '🛡️ 拦截成功 (Blocked)' }}
          </span>
        </div>
        <div class="card-content" style="flex:1; overflow-y:auto;">
          <p><span class="label" style="width:80px;">目标指令:</span> <span class="highlight-target">{{ currentQuery }}</span></p>
          <p><span class="label" style="width:80px;">EM 得分:</span> <span style="color: #38bdf8; font-weight: bold;">{{ attackResult.em_score }}</span> <span style="color:#64748b; font-size:12px;">(1表示模型成功被诱导拼凑出了目标词)</span></p>
          <p style="margin-top: 15px;"><span class="label" style="width:80px;">生成攻击词:</span></p>
          <pre style="background: #05070a; color: #94a3b8; padding: 10px; border-radius: 4px; font-family: inherit;">{{ attackResult.prompt }}</pre>
          <p style="margin-top: 15px;"><span class="label" style="width:80px;">靶机回复:</span></p>
          <pre style="background: #05070a; color: #ef4444; padding: 10px; border-radius: 4px; font-family: inherit;">{{ attackResult.response }}</pre>
        </div>
      </div>
      
      <div v-else-if="!loading" class="terminal-screen" style="display:flex; justify-content:center; align-items:center; flex:1;">
        <div class="idle-text">>> SYSTEM READY. 等待攻击指令...</div>
      </div>
      <div v-else class="terminal-screen green-theme" style="display:flex; justify-content:center; align-items:center; flex:1;">
        <div class="idle-text"><span class="pulse-dot"></span> 正在构建字谜与重构矩阵...<br>等待模型生成回复，这可能需要几十秒...</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const targetModel = ref('ollama-deepseek-r1:latest')
const behaviors = ref([])
const currentQuery = ref('')
const loading = ref(false)
const attackResult = ref(null)

onMounted(async () => {
  try {
    const res = await fetch('/api/dra/behaviors')
    const data = await res.json()
    if (data.code === 200) {
      behaviors.value = data.data.slice(0, 30) // 为了不卡，前端先展示前30条
    }
  } catch (err) {
    console.error("加载behaviors失败", err)
  }
})

const selectBehavior = (item) => {
  currentQuery.value = item
  attackResult.value = null
}

const runAttack = async () => {
  loading.value = true
  attackResult.value = null
  try {
    const res = await fetch('http://172.18.20.8:8000/api/dra/attack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: currentQuery.value, model: targetModel.value })
    })
    const data = await res.json()
    if(data.code === 200) {
      attackResult.value = data
    } else {
      alert("攻击执行异常: " + data.msg)
    }
  } catch (error) {
    alert("网络错误: " + error)
  }
  loading.value = false
}
</script>