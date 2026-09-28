import { lazy, Suspense } from 'react'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import LoadingState from './components/LoadingState'

// 路由级懒加载：各页面独立拆包，首屏只加载当前页面所需 chunk，
// 显著降低首屏 JS 体积（原实现为静态导入，所有页面打进一个 bundle）
const Home = lazy(() => import('./pages/Home'))
const Chat = lazy(() => import('./pages/Chat'))
const News = lazy(() => import('./pages/News'))
const NewsDetail = lazy(() => import('./pages/NewsDetail'))
const Feedback = lazy(() => import('./pages/Feedback'))
const Recommend = lazy(() => import('./pages/Recommend'))
const Profile = lazy(() => import('./pages/Profile'))
const Login = lazy(() => import('./pages/Login'))
const Itinerary = lazy(() => import('./pages/Itinerary'))
const Notifications = lazy(() => import('./pages/Notifications'))
const Analysis = lazy(() => import('./pages/Analysis'))
const MyKnowledge = lazy(() => import('./pages/MyKnowledge'))

// 懒加载兜底：页面 chunk 下载期间既要占位、也要说明在等什么
// （只有一个转圈时，用户无法判断是"在加载"还是"页面坏了"）
function PageLoading() {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '45vh',
      }}
    >
      <LoadingState text="页面加载中…" hint="首次打开需要下载页面资源，通常 1~2 秒" />
    </div>
  )
}

function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#3b5b8c',
          colorInfo: '#3b5b8c',
          colorBgBase: '#f5f3ee',
          colorBgContainer: '#fffdf9',
          colorBgElevated: '#fffdf9',
          colorBorder: '#e6e1d6',
          colorBorderSecondary: '#e6e1d6',
          colorText: '#2e2b26',
          colorTextSecondary: '#6b665c',
          colorTextTertiary: '#9a9488',
          borderRadius: 12,
          fontSize: 14,
          fontFamily:
            "'Noto Sans SC', 'Hiragino Sans', 'PingFang SC', 'Microsoft YaHei', sans-serif",
        },
        components: {
          Button: {
            colorPrimary: '#3b5b8c',
            colorPrimaryHover: '#4a6ea3',
            colorPrimaryActive: '#2e4a73',
            primaryShadow: 'none',
          },
          Card: {
            colorBgContainer: '#fffdf9',
            colorBorderSecondary: '#e6e1d6',
          },
          Menu: {
            colorBgContainer: 'transparent',
            itemSelectedColor: '#3b5b8c',
            itemSelectedBg: 'rgba(59, 91, 140, 0.08)',
            itemColor: '#6b665c',
            itemHoverColor: '#3b5b8c',
          },
          Input: {
            colorBgContainer: '#fffdf9',
            colorBorder: '#d8d1c2',
            colorPrimaryHover: '#3b5b8c',
            activeShadow: 'none',
          },
          Segmented: {
            itemSelectedBg: '#3b5b8c',
            itemSelectedColor: '#fffdf9',
            trackBg: '#f9f7f1',
          },
          Tag: {
            colorBgContainer: 'rgba(59, 91, 140, 0.06)',
          },
        },
      }}
    >
      <BrowserRouter>
        <Suspense fallback={<PageLoading />}>
          <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<MainLayout />}>
            <Route path="/" element={<Home />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/news" element={<News />} />
            <Route path="/news/:id" element={<NewsDetail />} />
            <Route path="/feedback" element={<Feedback />} />
            <Route path="/recommend" element={<Recommend />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/itinerary" element={<Itinerary />} />
            <Route path="/notifications" element={<Notifications />} />
            <Route path="/analysis" element={<Analysis />} />
            <Route path="/my-knowledge" element={<MyKnowledge />} />
          </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ConfigProvider>
  )
}

export default App
