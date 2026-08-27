import * as THREE from 'three'

// 城市地面：绿色草地平面 + 灰色道路网格
export function buildGround(): THREE.Group {
  const group = new THREE.Group()

  // 草地平面
  const groundGeo = new THREE.PlaneGeometry(60, 60)
  const groundMat = new THREE.MeshStandardMaterial({ color: 0x4a7c4a, roughness: 0.9 })
  const ground = new THREE.Mesh(groundGeo, groundMat)
  ground.rotation.x = -Math.PI / 2
  ground.receiveShadow = true
  group.add(ground)

  // 道路网格线（用 GridHelper 模拟城市道路）
  const grid = new THREE.GridHelper(60, 30, 0x888888, 0x666666)
  grid.position.y = 0.01
  group.add(grid)

  return group
}
