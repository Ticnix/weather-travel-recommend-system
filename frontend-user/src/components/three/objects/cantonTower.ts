import * as THREE from 'three'

/**
 * 广州塔（小蛮腰）简化模型：
 * - 用多个逐渐收窄的圆柱段堆叠，模拟"小蛮腰"的腰身曲线
 * - 顶部天线 + 底部观光平台
 */
export function buildCantonTower(): THREE.Group {
  const group = new THREE.Group()
  const metal = new THREE.MeshStandardMaterial({
    color: 0xcccccc,
    metalness: 0.6,
    roughness: 0.3,
  })

  // 塔身：从下往上堆叠圆柱段，半径先收窄再略微放宽（小蛮腰曲线）
  const segments = [
    { y: 0.5, r: 1.6 },
    { y: 2.0, r: 1.2 },
    { y: 3.5, r: 0.8 },
    { y: 5.0, r: 0.55 },
    { y: 6.5, r: 0.6 },
    { y: 8.0, r: 0.7 },
    { y: 9.5, r: 0.75 },
  ]

  let prevY = 0
  for (const seg of segments) {
    const height = seg.y - prevY
    const geo = new THREE.CylinderGeometry(seg.r, seg.r, height, 24)
    const mesh = new THREE.Mesh(geo, metal)
    mesh.position.y = prevY + height / 2
    mesh.castShadow = true
    group.add(mesh)
    prevY = seg.y
  }

  // 顶部天线
  const antennaGeo = new THREE.CylinderGeometry(0.06, 0.06, 3, 8)
  const antenna = new THREE.Mesh(antennaGeo, metal)
  antenna.position.y = 9.5 + 1.5
  group.add(antenna)

  // 底部观光平台（圆环）
  const deckGeo = new THREE.CylinderGeometry(2.0, 2.0, 0.3, 32)
  const deck = new THREE.Mesh(deckGeo, metal)
  deck.position.y = 0.15
  group.add(deck)

  // 整体放在场景中央
  group.position.set(0, 0, 0)
  return group
}
