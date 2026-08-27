import * as THREE from 'three'

export type WeatherType = 'sunny' | 'rain' | 'cloudy' | 'fog' | 'hot' | 'unknown'

export interface ParticleSystem {
  object: THREE.Points
  update: (delta: number) => void
  dispose: () => void
}

// 粒子系统覆盖范围
const AREA = { x: 30, y: 20, z: 30 }

/**
 * 根据天气类型创建粒子系统。
 * - sunny：上升的细小光斑（模拟阳光浮尘）
 * - rain：下落的雨滴线条
 * - cloudy：缓慢飘动的云絮
 * - fog：静止弥漫的雾粒
 * - hot：上升的热浪粒子
 */
export function createWeatherParticles(type: WeatherType): ParticleSystem {
  switch (type) {
    case 'rain':
      return createRain()
    case 'cloudy':
      return createCloud()
    case 'fog':
      return createFog()
    case 'hot':
      return createHot()
    case 'sunny':
    default:
      return createSunny()
  }
}

// ---------- 晴天：上升光斑 ----------
function createSunny(): ParticleSystem {
  const count = 300
  const positions = new Float32Array(count * 3)
  const speeds = new Float32Array(count)

  for (let i = 0; i < count; i++) {
    positions[i * 3] = (Math.random() - 0.5) * AREA.x
    positions[i * 3 + 1] = Math.random() * AREA.y
    positions[i * 3 + 2] = (Math.random() - 0.5) * AREA.z
    speeds[i] = 0.3 + Math.random() * 0.5
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

  const material = new THREE.PointsMaterial({
    color: 0xffe680,
    size: 0.08,
    transparent: true,
    opacity: 0.7,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  })

  const points = new THREE.Points(geometry, material)

  return {
    object: points,
    update: (delta) => {
      const pos = geometry.getAttribute('position') as THREE.BufferAttribute
      for (let i = 0; i < count; i++) {
        pos.setY(i, pos.getY(i) + speeds[i] * delta)
        if (pos.getY(i) > AREA.y) pos.setY(i, 0)
      }
      pos.needsUpdate = true
    },
    dispose: () => {
      geometry.dispose()
      material.dispose()
    },
  }
}

// ---------- 雨天：下落雨滴 ----------
function createRain(): ParticleSystem {
  const count = 1500
  const positions = new Float32Array(count * 3)
  const speeds = new Float32Array(count)

  for (let i = 0; i < count; i++) {
    positions[i * 3] = (Math.random() - 0.5) * AREA.x
    positions[i * 3 + 1] = Math.random() * AREA.y
    positions[i * 3 + 2] = (Math.random() - 0.5) * AREA.z
    speeds[i] = 20 + Math.random() * 15
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

  const material = new THREE.PointsMaterial({
    color: 0x9ec9ff,
    size: 0.15,
    transparent: true,
    opacity: 0.8,
    depthWrite: false,
  })

  const points = new THREE.Points(geometry, material)

  return {
    object: points,
    update: (delta) => {
      const pos = geometry.getAttribute('position') as THREE.BufferAttribute
      for (let i = 0; i < count; i++) {
        pos.setY(i, pos.getY(i) - speeds[i] * delta)
        if (pos.getY(i) < 0) {
          pos.setY(i, AREA.y)
          // 落地后重新随机水平位置，模拟雨滴落下再降
          pos.setX(i, (Math.random() - 0.5) * AREA.x)
          pos.setZ(i, (Math.random() - 0.5) * AREA.z)
        }
      }
      pos.needsUpdate = true
    },
    dispose: () => {
      geometry.dispose()
      material.dispose()
    },
  }
}

// ---------- 多云：漂浮云絮 ----------
function createCloud(): ParticleSystem {
  const count = 400
  const positions = new Float32Array(count * 3)
  const speeds = new Float32Array(count)

  for (let i = 0; i < count; i++) {
    positions[i * 3] = (Math.random() - 0.5) * AREA.x
    positions[i * 3 + 1] = AREA.y * 0.7 + Math.random() * AREA.y * 0.3
    positions[i * 3 + 2] = (Math.random() - 0.5) * AREA.z
    speeds[i] = 0.5 + Math.random() * 1.0
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

  const material = new THREE.PointsMaterial({
    color: 0xffffff,
    size: 0.8,
    transparent: true,
    opacity: 0.5,
    depthWrite: false,
  })

  const points = new THREE.Points(geometry, material)

  return {
    object: points,
    update: (delta) => {
      const pos = geometry.getAttribute('position') as THREE.BufferAttribute
      for (let i = 0; i < count; i++) {
        pos.setX(i, pos.getX(i) + speeds[i] * delta)
        if (pos.getX(i) > AREA.x / 2) pos.setX(i, -AREA.x / 2)
      }
      pos.needsUpdate = true
    },
    dispose: () => {
      geometry.dispose()
      material.dispose()
    },
  }
}

// ---------- 雾：弥漫雾粒 ----------
function createFog(): ParticleSystem {
  const count = 500
  const positions = new Float32Array(count * 3)

  for (let i = 0; i < count; i++) {
    positions[i * 3] = (Math.random() - 0.5) * AREA.x * 1.5
    positions[i * 3 + 1] = Math.random() * AREA.y * 0.6
    positions[i * 3 + 2] = (Math.random() - 0.5) * AREA.z * 1.5
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

  const material = new THREE.PointsMaterial({
    color: 0xcccccc,
    size: 1.2,
    transparent: true,
    opacity: 0.35,
    depthWrite: false,
  })

  const points = new THREE.Points(geometry, material)

  return {
    object: points,
    update: () => {
      // 雾基本静止，仅缓慢整体漂移
      points.rotation.y += 0.0005
    },
    dispose: () => {
      geometry.dispose()
      material.dispose()
    },
  }
}

// ---------- 高温：上升热浪 ----------
function createHot(): ParticleSystem {
  const count = 200
  const positions = new Float32Array(count * 3)
  const speeds = new Float32Array(count)

  for (let i = 0; i < count; i++) {
    positions[i * 3] = (Math.random() - 0.5) * AREA.x
    positions[i * 3 + 1] = Math.random() * AREA.y * 0.5
    positions[i * 3 + 2] = (Math.random() - 0.5) * AREA.z
    speeds[i] = 1.0 + Math.random() * 1.5
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

  const material = new THREE.PointsMaterial({
    color: 0xff9933,
    size: 0.2,
    transparent: true,
    opacity: 0.6,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  })

  const points = new THREE.Points(geometry, material)

  return {
    object: points,
    update: (delta) => {
      const pos = geometry.getAttribute('position') as THREE.BufferAttribute
      for (let i = 0; i < count; i++) {
        pos.setY(i, pos.getY(i) + speeds[i] * delta)
        if (pos.getY(i) > AREA.y * 0.5) pos.setY(i, 0)
      }
      pos.needsUpdate = true
    },
    dispose: () => {
      geometry.dispose()
      material.dispose()
    },
  }
}
