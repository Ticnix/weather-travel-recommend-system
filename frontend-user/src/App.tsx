import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import Home from './pages/Home'
import Chat from './pages/Chat'
import Placeholder from './pages/Placeholder'

function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 8,
        },
      }}
    >
      <BrowserRouter>
        <Routes>
          <Route element={<MainLayout />}>
            <Route path="/" element={<Home />} />
            <Route path="/chat" element={<Chat />} />
            <Route
              path="/news"
              element={
                <Placeholder title="气象资讯" description="气象资讯列表、详情、分类筛选将在后续接入。" />
              }
            />
            <Route
              path="/itinerary"
              element={
                <Placeholder title="我的行程" description="个人行程管理、天气提醒将在后续接入。" />
              }
            />
            <Route
              path="/profile"
              element={
                <Placeholder title="我的" description="个人信息、登录、我的反馈将在后续接入。" />
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}

export default App
