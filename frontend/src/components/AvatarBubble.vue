<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  src: { type: String, default: '' },
  name: { type: String, default: '同学' },
  size: { type: Number, default: 48 },
  online: { type: Boolean, default: false },
})

const imageFailed = ref(false)
const hasImage = computed(() => Boolean(props.src) && !imageFailed.value)

watch(() => props.src, () => {
  imageFailed.value = false
})
</script>

<template>
  <span
    class="avatar-bubble"
    :style="{ width: `${size}px`, height: `${size}px` }"
    role="img"
    :aria-label="hasImage ? `${name}的头像` : `${name}暂未设置头像`"
  >
    <img v-if="hasImage" :src="src" alt="" @error="imageFailed = true" />
    <span v-else class="avatar-placeholder" aria-hidden="true" />
    <i v-if="online" class="online-dot" aria-label="在线" />
  </span>
</template>
