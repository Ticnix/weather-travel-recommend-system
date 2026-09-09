import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import Home from './pages/Home'
import Chat from './pages/Chat'
import News from './pages/News'
import NewsDetail from './pages/NewsDetail'
import Feedback from './pages/Feedback'
import Recommend from './pages/Recommend'
import Profile from './pages/Profile'
import Login from './pages/Login'
import Placeholder from './pages/Placeholder'

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
            <Route
              path="/itinerary"
              element={
                <Placeholder title="我的行程" description="个人行程管理、天气提醒将在后续接入。" />
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}

export default App
