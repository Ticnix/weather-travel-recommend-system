import * as THREE from 'three'

// 建筑群：随机生成若干栋不同高度/颜色的楼，营造城市天际线
export function buildBuildings(): THREE.Group {
  const group = new THREE.Group()

  const colors = [0x8a9bb0, 0x7c8ea0, 0x9aa7b5, 0x6f7f90, 0xb0bcc8, 0x95a5b3]
  const count = 30

  for (let i = 0; i < count; i++) {
    const width = 1.0 + Math.random() * 1.5
    const depth = 1.0 + Math.random() * 1.5
    const height = 1.5 + Math.random() * 6

    const geo = new THREE.BoxGeometry(width, height, depth)
    const mat = new THREE.MeshStandardMaterial({
      color: colors[Math.floor(Math.random() * colors.length)],
      roughness: 0.8,
    })
    const building = new THREE.Mesh(geo, mat)
    building.position.set(
      (Math.random() - 0.5) * 40,
      height / 2,
      (Math.random() - 0.5) * 40,
    )
    building.castShadow = true
    building.receiveShadow = true

    // 避开中央广州塔区域
    const distFromCenter = Math.hypot(building.position.x, building.position.z)
    if (distFromCenter < 5) continue

    group.add(building)
  }

  return group
}
