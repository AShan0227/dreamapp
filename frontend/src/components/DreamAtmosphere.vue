<template>
  <!-- Full-screen cinematic atmosphere layer.
       Place once near the root of any page that wants the dream backdrop.
       Props let you dial the intensity per page. -->
  <view class="dream-atmosphere" :class="['atm-' + variant]">
    <!-- Layer 0: Aurora / moonrise background -->
    <view class="atm-aurora"></view>

    <!-- Layer 1: Multi-depth starfield (parallax) -->
    <view class="atm-stars">
      <view
        v-for="(s, i) in stars"
        :key="i"
        class="atm-star"
        :class="'atm-star-' + s.layer"
        :style="{ top: s.top + '%', left: s.left + '%', animationDelay: s.delay + 's' }"
      ></view>
    </view>

    <!-- Layer 2: Drifting pollen / dust motes (only on warm variants) -->
    <view v-if="pollen" class="atm-pollen">
      <view
        v-for="(p, i) in pollens"
        :key="'p' + i"
        class="dc-pollen"
        :style="{
          top: p.top + '%',
          left: p.left + '%',
          animationDelay: p.delay + 's',
          '--dc-pollen-dx': p.dx + 'rpx',
          '--dc-pollen-dy': p.dy + 'vh',
        }"
      ></view>
    </view>

    <!-- Layer 3: Soft volumetric light rays (optional) -->
    <view v-if="rays" class="atm-rays"></view>

    <!-- Layer 4: Film grain -->
    <view class="dc-grain" :class="{ 'dc-grain-strong': grainStrong }"></view>

    <!-- Layer 5: Vignette -->
    <view class="dc-vignette"></view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  /** Color preset — maps to film reference gradient. */
  variant?: 'moonrise' | 'inception' | 'spirited' | 'shinkai' | 'mulholland' | 'solaris'
  /** Number of stars (default 50). */
  starCount?: number
  /** Show drifting pollen (warm/lantern feel). */
  pollen?: boolean
  /** Show volumetric god-rays. */
  rays?: boolean
  /** Stronger film grain. */
  grainStrong?: boolean
}
const props = withDefaults(defineProps<Props>(), {
  variant: 'moonrise',
  starCount: 60,
  pollen: false,
  rays: false,
  grainStrong: false,
})

// Pre-compute star positions + 3 parallax layers once
const stars = computed(() =>
  Array.from({ length: props.starCount }, (_, i) => ({
    top: Math.random() * 100,
    left: Math.random() * 100,
    layer: (i % 3) as 0 | 1 | 2,
    delay: Math.random() * 4,
  })),
)

const pollens = computed(() =>
  Array.from({ length: 14 }, () => ({
    top: 80 + Math.random() * 20,      // start near bottom
    left: Math.random() * 100,
    delay: Math.random() * 18,
    dx: (Math.random() - 0.5) * 120,   // lateral drift
    dy: 100 + Math.random() * 30,      // rise up and off-screen
  })),
)
</script>

<style scoped>
.dream-atmosphere {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

/* Aurora gradient background, variant per film */
.atm-aurora {
  position: absolute;
  inset: 0;
  filter: saturate(1.15);
  animation: atm-aurora-breathe 24s ease-in-out infinite;
}
.atm-moonrise   .atm-aurora {
  background:
    radial-gradient(ellipse 60% 40% at 20% 10%, rgba(236,72,153,0.22), transparent 60%),
    radial-gradient(ellipse 70% 50% at 80% 20%, rgba(6,182,212,0.18), transparent 65%),
    radial-gradient(ellipse 80% 60% at 50% 100%, rgba(139,92,246,0.28), transparent 70%),
    var(--dc-grad-moonrise);
}
.atm-inception  .atm-aurora { background: var(--dc-grad-inception); }
.atm-spirited   .atm-aurora {
  background:
    radial-gradient(ellipse 70% 50% at 50% 90%, rgba(249,160,63,0.45), transparent 65%),
    var(--dc-grad-spirited);
}
.atm-shinkai    .atm-aurora {
  background:
    radial-gradient(ellipse 60% 40% at 50% 100%, rgba(249,210,110,0.35), transparent 65%),
    var(--dc-grad-shinkai);
}
.atm-mulholland .atm-aurora { background: var(--dc-grad-mulholland); }
.atm-solaris    .atm-aurora {
  background:
    radial-gradient(ellipse 60% 40% at 50% 100%, rgba(58,106,111,0.5), transparent 65%),
    var(--dc-grad-solaris);
}

@keyframes atm-aurora-breathe {
  0%, 100% { filter: saturate(1.15) hue-rotate(0deg); }
  50%      { filter: saturate(1.3) hue-rotate(8deg); }
}

/* Stars — 3 layers, different size/opacity/speed */
.atm-stars { position: absolute; inset: 0; }
.atm-star {
  position: absolute;
  border-radius: 50%;
  background: white;
  animation: atm-twinkle 3.5s ease-in-out infinite;
}
.atm-star-0 { width: 2rpx; height: 2rpx; opacity: 0.35; }
.atm-star-1 { width: 3rpx; height: 3rpx; opacity: 0.55; }
.atm-star-2 {
  width: 4rpx; height: 4rpx; opacity: 0.7;
  background: radial-gradient(circle, #f8f4ff 0%, rgba(196,181,253,0.9) 60%, transparent 100%);
  box-shadow: 0 0 8rpx rgba(196,181,253,0.7);
}
@keyframes atm-twinkle {
  0%, 100% { opacity: var(--twinkle-low, 0.2); transform: scale(1); }
  50%      { opacity: 1; transform: scale(1.35); }
}

/* Pollen container just holds the particles absolutely */
.atm-pollen { position: absolute; inset: 0; }

/* Volumetric rays — two diagonal shafts, subtle */
.atm-rays {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(105deg,
      transparent 30%, rgba(249,210,110,0.06) 40%, rgba(249,210,110,0.11) 50%, rgba(249,210,110,0.06) 60%, transparent 70%),
    linear-gradient(80deg,
      transparent 55%, rgba(196,181,253,0.05) 65%, transparent 75%);
  mix-blend-mode: screen;
  animation: atm-rays-drift 16s ease-in-out infinite;
}
@keyframes atm-rays-drift {
  0%, 100% { transform: translateX(-2%); opacity: 0.85; }
  50%      { transform: translateX(2%); opacity: 1; }
}
</style>
