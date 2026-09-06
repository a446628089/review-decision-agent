import type { RouteObject } from 'react-router-dom'
import { AppLayout } from '@/components/layout/app-layout'
export const routes: RouteObject[] = [{ path: "/", element: <AppLayout />, children: [
  { index: true, element: <div>研发评审智能决策平台</div> },
] }]
