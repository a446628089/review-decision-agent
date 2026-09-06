import type { RouteObject } from 'react-router-dom'
import { AppLayout } from '@/components/layout/app-layout'
import { lazy } from 'react'
const MeetingListPage = lazy(() => import('@/features/meetings/pages/meeting-list-page'))
const MeetingDetailPage = lazy(() => import('@/features/meetings/pages/meeting-detail-page'))
export const routes: RouteObject[] = [{ path: "/", element: <AppLayout />, children: [
  { index: true, element: <MeetingListPage /> },
  { path: "meetings/:id", element: <MeetingDetailPage /> },
] }]
