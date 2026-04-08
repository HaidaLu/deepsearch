import IconSendThunder from '@/assets/component/send-thunder.svg'
import { FileOutlined } from '@ant-design/icons'
import { Button, Input, Space } from 'antd'
import classNames from 'classnames'
import { PropsWithChildren, useState } from 'react'
import './index.scss'
import Recorder from './recorder'
import Uploader from './uploader'

export default function ComSender(
  props: PropsWithChildren<{
    className?: string
    loading?: boolean
    onSend?: (value: string) => void | Promise<void>
    onContract?: () => void
    sessionId?: string
    uploadedDoc?: { document_name: string } | null
    onUploadSuccess?: (file: File) => void
  }>,
) {
  const { className, onSend, onContract, loading, sessionId, uploadedDoc, onUploadSuccess, ...rest } = props
  const [value, setValue] = useState('')

  async function send() {
    if (loading) return
    if (!value) return
    await onSend?.(value)
    setValue('')
  }

  return (
    <div className={classNames('com-sender', className)} {...rest}>
      <Input.TextArea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault()
            send()
          }
        }}
        placeholder="Enter your question... (Ctrl+Enter to send)"
        autoSize={{ minRows: 2 }}
        autoFocus
      />

      <div className="com-sender__actions">
        <Space className="com-sender__actions-left" size={12}>
          <Recorder
            onMessage={(text) => {
              setValue(text)
            }}
          />
        </Space>

        <Space className="com-sender__actions-right" size={12}>
          {sessionId ? (
            uploadedDoc ? (
              <Button
                className="com-sender__action--contract"
                variant="text"
                color="default"
                shape="round"
                disabled
                title={uploadedDoc.document_name}
              >
                <FileOutlined style={{ fontSize: 14 }} />
                <span className="document-name">
                  {uploadedDoc.document_name}
                </span>
              </Button>
            ) : (
              <Uploader
                sessionId={sessionId}
                onSuccess={(file) => onUploadSuccess?.(file)}
              />
            )
          ) : null}
          <Button
            className="com-sender__action--send"
            variant="solid"
            color="primary"
            shape="round"
            onClick={send}
            loading={loading}
          >
            Send
            <img src={IconSendThunder} />
          </Button>
        </Space>
      </div>
    </div>
  )
}
