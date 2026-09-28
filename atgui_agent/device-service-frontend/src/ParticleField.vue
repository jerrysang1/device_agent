<script setup>
import { onMounted, onUnmounted, ref } from 'vue'

const canvasRef = ref(null)
const glowRef = ref(null)
const orbA = ref(null)
const orbB = ref(null)
const orbC = ref(null)

let rafId = 0
let particles = []
let width = 0
let height = 0
let dpr = 1
let mouse = { x: -9999, y: -9999, active: false }
let glowX = -200
let glowY = -200
let glowRaf = 0

const PARTICLE_COUNT = 95
const CONNECT_DIST = 120
const REPEL_RADIUS = 130
const REPEL_STRENGTH = 0.055

function resize() {
  const canvas = canvasRef.value
  if (!canvas) return
  dpr = Math.min(window.devicePixelRatio || 1, 2)
  width = window.innerWidth
  height = window.innerHeight
  canvas.width = Math.floor(width * dpr)
  canvas.height = Math.floor(height * dpr)
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`
  const ctx = canvas.getContext('2d')
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function seedParticles() {
  particles = Array.from({ length: PARTICLE_COUNT }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * 0.32,
    vy: (Math.random() - 0.5) * 0.32,
    r: 1.6 + Math.random() * 2.8,
    a: 0.28 + Math.random() * 0.38,
  }))
}

function onPointerMove(event) {
  mouse.x = event.clientX
  mouse.y = event.clientY
  mouse.active = true

  const glow = glowRef.value
  if (glow) {
    cancelAnimationFrame(glowRaf)
    glowRaf = requestAnimationFrame(() => {
      glowX += (mouse.x - glowX) * 0.18
      glowY += (mouse.y - glowY) * 0.18
      glow.style.transform = `translate3d(${glowX - 80}px, ${glowY - 80}px, 0)`
    })
  }

  const cx = mouse.x - window.innerWidth / 2
  const cy = mouse.y - window.innerHeight / 2
  if (orbA.value) {
    orbA.value.style.transform = `translate3d(${cx * 0.035}px, ${cy * 0.035}px, 0)`
  }
  if (orbB.value) {
    orbB.value.style.transform = `translate3d(${cx * -0.05}px, ${cy * 0.04}px, 0)`
  }
  if (orbC.value) {
    orbC.value.style.transform = `translate3d(${cx * 0.028}px, ${cy * -0.032}px, 0)`
  }
}

function onPointerLeave() {
  mouse.active = false
  mouse.x = -9999
  mouse.y = -9999
}

function step() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  ctx.clearRect(0, 0, width, height)

  for (const p of particles) {
    if (mouse.active) {
      const dx = p.x - mouse.x
      const dy = p.y - mouse.y
      const dist = Math.hypot(dx, dy) || 0.001
      if (dist < REPEL_RADIUS) {
        const force = (1 - dist / REPEL_RADIUS) * REPEL_STRENGTH
        p.vx += (dx / dist) * force * 8
        p.vy += (dy / dist) * force * 8
      }
    }

    p.vx *= 0.98
    p.vy *= 0.98
    p.x += p.vx
    p.y += p.vy

    if (p.x < -10) p.x = width + 10
    if (p.x > width + 10) p.x = -10
    if (p.y < -10) p.y = height + 10
    if (p.y > height + 10) p.y = -10

    ctx.beginPath()
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(13, 148, 136, ${p.a})`
    ctx.fill()
  }

  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const a = particles[i]
      const b = particles[j]
      const dx = a.x - b.x
      const dy = a.y - b.y
      const dist = Math.hypot(dx, dy)
      if (dist < CONNECT_DIST) {
        const alpha = (1 - dist / CONNECT_DIST) * 0.18
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        ctx.strokeStyle = `rgba(13, 148, 136, ${alpha})`
        ctx.lineWidth = 1
        ctx.stroke()
      }
    }
  }

  if (mouse.active) {
    for (const p of particles) {
      const dx = p.x - mouse.x
      const dy = p.y - mouse.y
      const dist = Math.hypot(dx, dy)
      if (dist < REPEL_RADIUS * 1.15) {
        const alpha = (1 - dist / (REPEL_RADIUS * 1.15)) * 0.28
        ctx.beginPath()
        ctx.moveTo(p.x, p.y)
        ctx.lineTo(mouse.x, mouse.y)
        ctx.strokeStyle = `rgba(15, 118, 110, ${alpha})`
        ctx.lineWidth = 1
        ctx.stroke()
      }
    }
  }

  rafId = requestAnimationFrame(step)
}

onMounted(() => {
  resize()
  seedParticles()
  window.addEventListener('resize', resize)
  window.addEventListener('pointermove', onPointerMove, { passive: true })
  window.addEventListener('pointerleave', onPointerLeave)
  rafId = requestAnimationFrame(step)
})

onUnmounted(() => {
  cancelAnimationFrame(rafId)
  cancelAnimationFrame(glowRaf)
  window.removeEventListener('resize', resize)
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerleave', onPointerLeave)
})
</script>

<template>
  <div class="particle-layer" aria-hidden="true">
    <div ref="orbA" class="orb orb-a"></div>
    <div ref="orbB" class="orb orb-b"></div>
    <div ref="orbC" class="orb orb-c"></div>
    <canvas ref="canvasRef" class="particle-canvas"></canvas>
    <div ref="glowRef" class="cursor-glow"></div>
  </div>
</template>

<style scoped>
.particle-layer {
  position: fixed;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  overflow: hidden;
}

.particle-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0.78;
  mix-blend-mode: multiply;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(2px);
  opacity: 0.45;
  will-change: transform;
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.orb-a {
  width: 120px;
  height: 120px;
  top: 12%;
  left: 8%;
  background: radial-gradient(circle, rgba(45, 212, 191, 0.55), rgba(45, 212, 191, 0));
}

.orb-b {
  width: 90px;
  height: 90px;
  top: 58%;
  left: 22%;
  background: radial-gradient(circle, rgba(56, 189, 248, 0.4), rgba(56, 189, 248, 0));
}

.orb-c {
  width: 140px;
  height: 140px;
  top: 30%;
  right: 8%;
  background: radial-gradient(circle, rgba(20, 184, 166, 0.4), rgba(20, 184, 166, 0));
}

.cursor-glow {
  position: absolute;
  top: 0;
  left: 0;
  width: 160px;
  height: 160px;
  border-radius: 50%;
  background: radial-gradient(
    circle,
    rgba(13, 148, 136, 0.2) 0%,
    rgba(13, 148, 136, 0.07) 40%,
    transparent 70%
  );
  transform: translate3d(-300px, -300px, 0);
  will-change: transform;
  transition: opacity 0.3s ease;
  opacity: 1;
}
</style>
