import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { hasRole, useAuth } from './lib/auth'
import AgentsPage from './pages/AgentsPage'
import EditorPage from './pages/EditorPage'
import KnowledgeDetailPage from './pages/KnowledgeDetailPage'
import KnowledgePage from './pages/KnowledgePage'
import LoginPage from './pages/LoginPage'
import ScenariosPage from './pages/ScenariosPage'
import TagsPage from './pages/TagsPage'
import UsersPage from './pages/UsersPage'

function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuth((s) => s.token)
  return token ? children : <Navigate to="/login" replace />
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const user = useAuth((s) => s.user)
  return hasRole(user, 'admin') ? children : <Navigate to="/" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<AgentsPage />} />
        <Route path="agents/:agentId" element={<EditorPage />} />
        <Route path="agents/:agentId/scenarios" element={<ScenariosPage />} />
        <Route path="knowledge" element={<KnowledgePage />} />
        <Route path="knowledge/tags" element={<TagsPage />} />
        <Route path="knowledge/:kbId" element={<KnowledgeDetailPage />} />
        <Route
          path="users"
          element={
            <RequireAdmin>
              <UsersPage />
            </RequireAdmin>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
