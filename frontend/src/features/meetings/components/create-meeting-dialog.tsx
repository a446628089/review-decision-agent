import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogFooter } from '@/components/ui/dialog'
import { useCreateMeeting } from '../hooks/use-meetings'

interface CreateMeetingDialogProps {
  open: boolean
  onClose: () => void
}

export function CreateMeetingDialog({ open, onClose }: CreateMeetingDialogProps) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [participants, setParticipants] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState('')

  const createMeeting = useCreateMeeting()

  const resetForm = () => {
    setTitle('')
    setDescription('')
    setParticipants('')
    setIsUploading(false)
    setError('')
  }

  const handleClose = () => {
    if (isUploading) return
    resetForm()
    onClose()
  }

  const handleSubmit = async () => {
    setError('')

    if (!title.trim()) {
      setError('请输入会议标题')
      return
    }

    try {
      await createMeeting.mutateAsync({
        title: title.trim(),
        description: description.trim() || undefined,
        participants: participants
          ? participants.split(',').map((p) => p.trim()).filter(Boolean)
          : undefined,
      })

      resetForm()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      title="新建会议"
      description="创建研发评审会议"
      closeOnOverlayClick={!isUploading}
    >
      <div className="space-y-5">
        {/* 标题 */}
        <div className="space-y-2">
          <Label htmlFor="title">
            会议标题 <span className="text-destructive">*</span>
          </Label>
          <Input
            id="title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="例如：Q3 产品规划讨论"
            autoFocus
          />
        </div>

        {/* 描述 */}
        <div className="space-y-2">
          <Label htmlFor="description">会议描述</Label>
          <Textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="简要描述会议内容..."
            rows={3}
          />
        </div>

        {/* 参会人 */}
        <div className="space-y-2">
          <Label htmlFor="participants">参会人员</Label>
          <Input
            id="participants"
            value={participants}
            onChange={(e) => setParticipants(e.target.value)}
            placeholder="用逗号分隔，如：张三, 李四, 王五"
          />
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={handleClose} disabled={isUploading}>
          取消
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={isUploading || createMeeting.isPending}
        >
          {isUploading
            ? '保存中'
            : createMeeting.isPending
              ? '创建中...'
              : '创建会议'}
        </Button>
      </DialogFooter>
    </Dialog>
  )
}
