import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { buildGround } from './objects/ground'
import { buildCantonTower } from './objects/cantonTower'
import { buildBuildings } from './objects/buildings'
import {
  createWeatherParticles,
  type ParticleSystem,
  type WeatherType,
} from './effects/weatherParticles'

interface WeatherSceneProps {
  weatherType: WeatherType
}

// 天气类型 → 天空色 / 雾色
const SKY_COLORS: Record<WeatherType, string> = {
  sunny: '#87ceeb',
  rain: '#4a5a6a',
  cloudy: '#a0b8c8',
  fog: '#b8c0c8',
  hot: '#f5a623',
  unknown: '#87ceeb',
}

/**
 * 3D 天气可视化场景（原生 Three.js 实现）。
 *
 * 结构：
 *   Scene + PerspectiveCamera + WebGLRenderer
 *   - 天空背景 / 雾（随天气变化）
 *   - AmbientLight + DirectionalLight
 *   - Ground（地面）、CantonTower（广州塔）、Buildings（建筑群）
 *   - WeatherParticles（粒子系统，随天气切换）
 *   - OrbitControls（旋转/缩放）
 *   - requestAnimationFrame 渲染循环
 *
 * 实现要点：
 *   - 用 useRef 拿容器 div，在 useEffect 里初始化 Three.js（避免重复挂载）
 *   - scene / particles 存到容器 DOM 的自定义属性上，供天气切换时复用
 *   - 天气变化时不重建整个场景，只切换粒子系统 + 更新天空色
 */
export default function WeatherScene({ weatherType }: WeatherSceneProps) {
  const mountRef = useRef<HTMLDivElement>(null)

  // 首次挂载：初始化 Three.js 场景（仅执行一次）
  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    // ---------- 1. 三大件 ----------
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(SKY_COLORS[weatherType])
    scene.fog = new THREE.Fog(SKY_COLORS[weatherType], 30, 90)

    const camera = new THREE.PerspectiveCamera(
      50,
      mount.clientWidth / mount.clientHeight,
      0.1,
      200,
    )
    camera.position.set(14, 9, 18)

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setSize(mount.clientWidth, mount.clientHeight)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.shadowMap.enabled = true
    mount.appendChild(renderer.domElement)

    // ---------- 2. 光照 ----------
    scene.add(new THREE.AmbientLight(0xffffff, 0.6))

    const dirLight = new THREE.DirectionalLight(0xffffff, 1.2)
    dirLight.position.set(15, 20, 10)
    dirLight.castShadow = true
    dirLight.shadow.mapSize.set(1024, 1024)
    scene.add(dirLight)

    // ---------- 3. 场景对象 ----------
    scene.add(buildGround())
    scene.add(buildCantonTower())
    scene.add(buildBuildings())

    // ---------- 4. 粒子系统 ----------
    let particles: ParticleSystem = createWeatherParticles(weatherType)
    scene.add(particles.object)

    // ---------- 5. 轨道控制 ----------
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.target.set(0, 5, 0)
    controls.enableDamping = true
    controls.minDistance = 8
    controls.maxDistance = 45
    controls.maxPolarAngle = Math.PI / 2 - 0.05

    // ---------- 6. 渲染循环 ----------
    const clock = new THREE.Clock()
    let rafId = 0
    const animate = () => {
      rafId = requestAnimationFrame(animate)
      const delta = clock.getDelta()
      particles.update(delta)
      controls.update()
      renderer.render(scene, camera)
    }
    animate()

    // 把 scene/particles/renderer 挂到容器 DOM 上，供天气切换 effect 复用
    ;(mount as any).__scene = scene
    ;(mount as any).__particles = particles
    ;(mount as any).__renderer = renderer

    // ---------- 7. 响应式 & 清理 ----------
    const onResize = () => {
      camera.aspect = mount.clientWidth / mount.clientHeight
      camera.updateProjectionMatrix()
      renderer.setSize(mount.clientWidth, mount.clientHeight)
    }
    window.addEventListener('resize', onResize)

    return () => {
      cancelAnimationFrame(rafId)
      window.removeEventListener('resize', onResize)
      controls.dispose()
      particles.dispose()
      renderer.dispose()
      mount.removeChild(renderer.domElement)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 天气变化：更新天空色/雾 + 切换粒子系统（不重建场景）
  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return
    const scene = (mount as any).__scene as THREE.Scene | undefined
    const renderer = (mount as any).__renderer as THREE.WebGLRenderer | undefined
    if (!scene || !renderer) return

    const color = SKY_COLORS[weatherType]
    scene.background = new THREE.Color(color)
    if (scene.fog) scene.fog.color = new THREE.Color(color)

    const oldParticles = (mount as any).__particles as ParticleSystem | undefined
    if (oldParticles) {
      scene.remove(oldParticles.object)
      oldParticles.dispose()
    }
    const newParticles = createWeatherParticles(weatherType)
    scene.add(newParticles.object)
    ;(mount as any).__particles = newParticles
  }, [weatherType])

  return <div ref={mountRef} style={{ width: '100%', height: '100%' }} />
}
