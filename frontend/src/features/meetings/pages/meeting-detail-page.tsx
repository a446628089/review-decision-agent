import { useParams } from 'react-router-dom'
import { useMeeting } from '../hooks/use-meetings'
export default function MeetingDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: meeting, isLoading } = useMeeting(id)
  if (isLoading) return <p>加载中...</p>
  if (!meeting) return <p>会议不存在</p>
  return <div><h1>{meeting.title}</h1><p>{meeting.description}</p><p>{meeting.participants?.join('、')}</p></div>
}
