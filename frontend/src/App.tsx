import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { AddRecordPage } from './pages/AddRecordPage'
import { AdminPage } from './pages/AdminPage'
import { DocumentViewerPage } from './pages/DocumentViewerPage'
import { DoctorsPage } from './pages/DoctorsPage'
import { EditRecordPage } from './pages/EditRecordPage'
import { HomePage } from './pages/HomePage'
import { InvitePage } from './pages/InvitePage'
import { LabsPage } from './pages/LabsPage'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PrivacyPage } from './pages/PrivacyPage'
import { ProfilePage } from './pages/ProfilePage'
import { RecordDetailPage } from './pages/RecordDetailPage'
import { RecordsPage } from './pages/RecordsPage'
import { SearchPage } from './pages/SearchPage'
import { TimelinePage } from './pages/TimelinePage'

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

export function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/invite/:token" element={<InvitePage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route element={<AppLayout />}>
          <Route index element={<HomePage />} />
          <Route path="records" element={<RecordsPage />} />
          <Route path="records/:id" element={<RecordDetailPage />} />
          <Route path="records/:id/edit" element={<EditRecordPage />} />
          <Route path="timeline" element={<TimelinePage />} />
          <Route path="search" element={<SearchPage />} />
          <Route path="add" element={<AddRecordPage />} />
          <Route path="add/:type" element={<AddRecordPage />} />
          <Route path="documents/:id" element={<DocumentViewerPage />} />
          <Route path="doctors" element={<DoctorsPage />} />
          <Route path="labs" element={<LabsPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="admin" element={<AdminPage />} />
          <Route path="more" element={<Navigate to="/profile" replace />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </>
  )
}
