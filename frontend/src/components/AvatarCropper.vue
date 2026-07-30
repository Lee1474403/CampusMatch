<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  file: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const stage = ref(null)
const sourceImage = ref(null)
const objectUrl = ref('')
const naturalWidth = ref(0)
const naturalHeight = ref(0)
const stageSize = ref(320)
const zoom = ref(1)
const exporting = ref(false)
const offset = reactive({ x: 0, y: 0 })
const drag = reactive({ active: false, pointerId: null, startX: 0, startY: 0, originX: 0, originY: 0 })

const baseScale = computed(() => {
  if (!naturalWidth.value || !naturalHeight.value) return 1
  return Math.max(cropSize.value / naturalWidth.value, cropSize.value / naturalHeight.value)
})

const cropSize = computed(() => stageSize.value * 0.84)
const displayScale = computed(() => baseScale.value * zoom.value)
const displayWidth = computed(() => naturalWidth.value * displayScale.value)
const displayHeight = computed(() => naturalHeight.value * displayScale.value)
const ready = computed(() => Boolean(objectUrl.value && naturalWidth.value && naturalHeight.value))

const imageStyle = computed(() => ({
  width: `${displayWidth.value}px`,
  height: `${displayHeight.value}px`,
  transform: `translate3d(${offset.x}px, ${offset.y}px, 0)`,
}))

function revokeObjectUrl() {
  if (objectUrl.value) URL.revokeObjectURL(objectUrl.value)
  objectUrl.value = ''
}

function loadSource() {
  revokeObjectUrl()
  naturalWidth.value = 0
  naturalHeight.value = 0
  if (props.file) objectUrl.value = URL.createObjectURL(props.file)
}

function updateStageSize() {
  const size = stage.value?.clientWidth
  if (size) stageSize.value = size
  clampOffset()
}

function initializeCrop() {
  loadSource()
  nextTick(updateStageSize)
}

function onImageLoad(event) {
  naturalWidth.value = event.target.naturalWidth
  naturalHeight.value = event.target.naturalHeight
  resetCrop()
  nextTick(updateStageSize)
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function clampOffset() {
  const maxX = Math.max(0, (displayWidth.value - cropSize.value) / 2)
  const maxY = Math.max(0, (displayHeight.value - cropSize.value) / 2)
  offset.x = clamp(offset.x, -maxX, maxX)
  offset.y = clamp(offset.y, -maxY, maxY)
}

function resetCrop() {
  zoom.value = 1
  offset.x = 0
  offset.y = 0
}

function startDrag(event) {
  if (!ready.value) return
  drag.active = true
  drag.pointerId = event.pointerId
  drag.startX = event.clientX
  drag.startY = event.clientY
  drag.originX = offset.x
  drag.originY = offset.y
  event.currentTarget.setPointerCapture?.(event.pointerId)
}

function moveDrag(event) {
  if (!drag.active || event.pointerId !== drag.pointerId) return
  offset.x = drag.originX + event.clientX - drag.startX
  offset.y = drag.originY + event.clientY - drag.startY
  clampOffset()
}

function endDrag(event) {
  if (!drag.active || event.pointerId !== drag.pointerId) return
  drag.active = false
  drag.pointerId = null
  event.currentTarget.releasePointerCapture?.(event.pointerId)
}

function close() {
  emit('update:modelValue', false)
}

async function confirmCrop() {
  if (!ready.value || exporting.value) return
  exporting.value = true

  try {
    const outputSize = 512
    const ratio = outputSize / cropSize.value
    const canvas = document.createElement('canvas')
    canvas.width = outputSize
    canvas.height = outputSize
    const context = canvas.getContext('2d')
    const drawX = (cropSize.value - displayWidth.value) / 2 + offset.x
    const drawY = (cropSize.value - displayHeight.value) / 2 + offset.y

    context.imageSmoothingEnabled = true
    context.imageSmoothingQuality = 'high'
    context.drawImage(
      sourceImage.value,
      drawX * ratio,
      drawY * ratio,
      displayWidth.value * ratio,
      displayHeight.value * ratio,
    )

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92))
    if (!blob) throw new Error('头像裁剪失败')
    const croppedFile = new File([blob], 'avatar-cropped.jpg', { type: 'image/jpeg' })
    emit('confirm', croppedFile)
    close()
  } catch (error) {
    ElMessage.error(error.message || '头像裁剪失败，请重新选择图片')
  } finally {
    exporting.value = false
  }
}

watch(zoom, clampOffset)
watch(() => props.file, () => {
  if (props.modelValue) loadSource()
})

onBeforeUnmount(revokeObjectUrl)
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    class="avatar-crop-dialog"
    width="min(460px, calc(100vw - 24px))"
    align-center
    destroy-on-close
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
    @opened="initializeCrop"
    @closed="revokeObjectUrl"
  >
    <template #header>
      <div class="crop-dialog-title">
        <span>✦</span>
        <div><b>裁剪头像</b><small>拖动图片，保留你喜欢的部分</small></div>
      </div>
    </template>

    <div class="avatar-cropper">
      <div
        ref="stage"
        class="crop-stage"
        :class="{ dragging: drag.active }"
        @pointerdown="startDrag"
        @pointermove="moveDrag"
        @pointerup="endDrag"
        @pointercancel="endDrag"
      >
        <img
          v-if="objectUrl"
          ref="sourceImage"
          :src="objectUrl"
          :style="imageStyle"
          alt="待裁剪头像"
          draggable="false"
          @load="onImageLoad"
        />
        <div class="crop-ring" aria-hidden="true" />
      </div>

      <div class="crop-controls">
        <span aria-hidden="true">−</span>
        <el-slider v-model="zoom" :min="1" :max="3" :step="0.01" :show-tooltip="false" aria-label="头像缩放" />
        <span class="large-icon" aria-hidden="true">＋</span>
      </div>
      <div class="crop-help"><span>↔ 拖动调整位置</span><button type="button" @click="resetCrop">恢复居中</button></div>
    </div>

    <template #footer>
      <div class="crop-actions">
        <button type="button" class="secondary-pill" @click="close">取消</button>
        <button type="button" class="primary-pill" :disabled="!ready || exporting" @click="confirmCrop">
          {{ exporting ? '处理中…' : '确认并上传' }}
        </button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.crop-dialog-title { display: flex; align-items: center; gap: 11px; }
.crop-dialog-title > span { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 13px 13px 13px 4px; color: #25313c; background: #ffe66d; font-size: 18px; }
.crop-dialog-title > div { display: flex; flex-direction: column; }
.crop-dialog-title b { font: 600 19px 'Fredoka', 'Nunito', sans-serif; color: #25313c; }
.crop-dialog-title small { margin-top: 2px; color: #7d8790; font-size: 11px; }
.avatar-cropper { display: flex; flex-direction: column; align-items: center; padding-top: 4px; }
.crop-stage { position: relative; overflow: hidden; width: min(320px, calc(100vw - 72px)); aspect-ratio: 1; border-radius: 22px; background: #e9e6e2; cursor: grab; touch-action: none; user-select: none; }
.crop-stage.dragging { cursor: grabbing; }
.crop-stage img { position: absolute; left: 50%; top: 50%; display: block; max-width: none; max-height: none; object-fit: fill; pointer-events: none; user-select: none; translate: -50% -50%; will-change: transform; }
.crop-ring { position: absolute; left: 50%; top: 50%; width: 84%; aspect-ratio: 1; border: 3px solid rgba(255,255,255,.95); border-radius: 50%; box-shadow: 0 0 0 999px rgba(24,31,38,.58), inset 0 0 25px rgba(37,49,60,.08); pointer-events: none; transform: translate(-50%, -50%); }
.crop-controls { width: min(320px, 100%); display: grid; grid-template-columns: 24px 1fr 24px; align-items: center; gap: 10px; margin-top: 18px; color: #7d8790; font-weight: 800; }
.crop-controls > span { text-align: center; }
.crop-controls .large-icon { color: #25313c; font-size: 18px; }
.crop-help { width: min(320px, 100%); display: flex; justify-content: space-between; margin-top: 3px; color: #8b939a; font-size: 10px; }
.crop-help button { padding: 0; border: 0; color: #29aaa4; background: none; cursor: pointer; font-weight: 800; }
.crop-actions { display: flex; justify-content: flex-end; gap: 10px; }
.crop-actions button { min-width: 116px; }

@media (max-width: 480px) {
  .crop-actions { display: grid; grid-template-columns: 1fr 1.35fr; }
  .crop-actions button { min-width: 0; padding: 0 15px; }
}
</style>

<style>
.avatar-crop-dialog { border-radius: 25px !important; overflow: hidden; }
.avatar-crop-dialog .el-dialog__header { margin-right: 0; padding: 22px 24px 12px; }
.avatar-crop-dialog .el-dialog__body { padding: 10px 24px 16px; }
.avatar-crop-dialog .el-dialog__footer { padding: 4px 24px 22px; }
.avatar-crop-dialog .el-slider__bar { background: linear-gradient(90deg, #4ecdc4, #ff6b6b); }
.avatar-crop-dialog .el-slider__button { width: 18px; height: 18px; border: 4px solid #ff6b6b; }
</style>
