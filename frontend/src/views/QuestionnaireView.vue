<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Check, MagicStick } from '@element-plus/icons-vue'

import { api, errorMessage } from '../api/client'
import AppShell from '../components/AppShell.vue'

const loading = ref(true)
const saving = ref(false)
const questions = ref([])
const answers = reactive({})
const currentStep = ref(0)
const completed = ref(false)

const dimensionMeta = {
  性格与处事风格: { code: '01', emoji: '🫧', copy: '冲突、边界与表达方式' },
  金钱观与消费习惯: { code: '02', emoji: '🪙', copy: '储蓄、消费与共同生活' },
  就业与城市选择: { code: '03', emoji: '🧭', copy: '事业路径与未来落点' },
  家庭与亲情关系: { code: '04', emoji: '🏠', copy: '父母、距离与照顾责任' },
  生活方式与价值观: { code: '05', emoji: '🌿', copy: '日常习惯与长期价值观' },
}

const groups = computed(() => {
  const result = []
  for (const question of questions.value) {
    let group = result.find((item) => item.dimension === question.dimension)
    if (!group) {
      group = { dimension: question.dimension, questions: [], ...(dimensionMeta[question.dimension] || {}) }
      result.push(group)
    }
    group.questions.push(question)
  }
  return result
})

const currentGroup = computed(() => groups.value[currentStep.value] || null)
const answeredCount = computed(() => questions.value.filter((question) => answers[question.id]).length)
const progress = computed(() => questions.value.length ? Math.round(answeredCount.value / questions.value.length * 100) : 0)
const currentComplete = computed(() => currentGroup.value?.questions.every((question) => answers[question.id]) || false)
const allComplete = computed(() => questions.value.length > 0 && answeredCount.value === questions.value.length)

async function loadQuestionnaire() {
  try {
    const { data } = await api.get('/questionnaire')
    questions.value = data.questions
    Object.assign(answers, data.answers)
    completed.value = data.completed
    const firstIncomplete = groups.value.findIndex((group) => group.questions.some((question) => !answers[question.id]))
    currentStep.value = firstIncomplete >= 0 ? firstIncomplete : Math.max(0, groups.value.length - 1)
  } catch (error) {
    ElMessage.error(errorMessage(error, '问卷加载失败'))
  } finally {
    loading.value = false
  }
}

async function saveAnswers({ advance = false, finish = false } = {}) {
  if (advance && !currentComplete.value) {
    ElMessage.warning('请先完成本页全部题目')
    return
  }
  if (finish && !allComplete.value) {
    const firstIncomplete = groups.value.findIndex((group) => group.questions.some((question) => !answers[question.id]))
    if (firstIncomplete >= 0) currentStep.value = firstIncomplete
    ElMessage.warning('还有题目未完成，已为你定位到第一处')
    return
  }
  saving.value = true
  try {
    const payload = Object.entries(answers).map(([questionId, answerKey]) => ({
      question_id: Number(questionId),
      answer_key: answerKey,
    }))
    const { data } = await api.put('/questionnaire/answers', { answers: payload })
    completed.value = data.completed
    ElMessage.success(data.message)
    if (advance && currentStep.value < groups.value.length - 1) currentStep.value += 1
  } catch (error) {
    ElMessage.error(errorMessage(error, '问卷保存失败'))
  } finally {
    saving.value = false
  }
}

function previousStep() {
  if (currentStep.value > 0) currentStep.value -= 1
}

onMounted(loadQuestionnaire)
</script>

<template>
  <AppShell>
    <section class="questionnaire-page">
      <header class="questionnaire-hero">
        <div>
          <p class="eyebrow">Deep Match · 深度匹配</p>
          <h1>把重要的选择，<span>提前聊清楚</span></h1>
          <p>26 道情境题不会定义你，只帮助系统理解两个人面对真实生活时是否同频。</p>
        </div>
        <div class="questionnaire-progress-orbit" :class="{ complete: completed }">
          <el-progress type="circle" :percentage="progress" :width="112" :stroke-width="8" color="#4ECDC4" />
          <small>{{ answeredCount }}/{{ questions.length }} 已回答</small>
        </div>
      </header>

      <div v-if="loading" class="questionnaire-loading"><span /><span /><span /><p>正在展开问卷…</p></div>

      <div v-else class="questionnaire-layout">
        <aside class="questionnaire-map">
          <div class="ai-use-note"><el-icon><MagicStick /></el-icon><p><b>完成后自动启用</b><small>答案仅用于匹配计算；大模型评分失败时会回退到普通匹配。</small></p></div>
          <button
            v-for="(group, index) in groups"
            :key="group.dimension"
            :class="{ active: index === currentStep, done: group.questions.every((question) => answers[question.id]) }"
            @click="currentStep = index"
          >
            <i>{{ group.questions.every((question) => answers[question.id]) ? '✓' : group.code }}</i>
            <span><b>{{ group.dimension }}</b><small>{{ group.copy }}</small></span>
          </button>
          <router-link class="questionnaire-back" to="/profile">暂时不填，返回个人中心</router-link>
        </aside>

        <main v-if="currentGroup" class="questionnaire-sheet">
          <div class="questionnaire-sheet-head">
            <span>{{ currentGroup.emoji }}</span>
            <div><p>PART {{ currentGroup.code }}</p><h2>{{ currentGroup.dimension }}</h2><small>{{ currentGroup.copy }}</small></div>
            <b>{{ currentGroup.questions.filter((question) => answers[question.id]).length }}/{{ currentGroup.questions.length }}</b>
          </div>

          <div class="question-list">
            <article v-for="question in currentGroup.questions" :key="question.id" class="question-card" :class="{ answered: answers[question.id] }">
              <div class="question-number">{{ question.code }}</div>
              <div class="question-body">
                <h3>{{ question.prompt }}</h3>
                <el-radio-group v-model="answers[question.id]" class="question-options">
                  <el-radio v-for="option in question.options" :key="option.key" :value="option.key" border>
                    <span class="option-key">{{ option.key }}</span><span>{{ option.text }}</span>
                  </el-radio>
                </el-radio-group>
              </div>
            </article>
          </div>

          <footer class="questionnaire-actions">
            <button class="secondary-pill" :disabled="currentStep === 0" @click="previousStep"><el-icon><ArrowLeft /></el-icon> 上一部分</button>
            <button class="text-button" :disabled="saving" @click="saveAnswers()">{{ saving ? '保存中…' : '保存当前进度' }}</button>
            <button v-if="currentStep < groups.length - 1" class="primary-pill" :disabled="saving" @click="saveAnswers({ advance: true })">保存并继续 <el-icon><ArrowRight /></el-icon></button>
            <button v-else class="primary-pill" :disabled="saving" @click="saveAnswers({ finish: true })"><el-icon><Check /></el-icon> {{ completed ? '更新深度匹配答案' : '完成并启用深度匹配' }}</button>
          </footer>
        </main>
      </div>
    </section>
  </AppShell>
</template>
