import * as api from '@/api'
import IconFile from '@/assets/chat/file.svg'
import { CloseOutlined, PlusCircleOutlined } from '@ant-design/icons'
import { Button, Upload } from 'antd'
import styles from './source.module.scss'

const ACCEPT = ['pdf', 'doc', 'docx', 'txt', 'md', 'xlsx', 'xls', 'html', 'htm', 'json', 'pptx']

export default function Source(props: {
  list: API.Document[]
  sessionId?: string
  onRemove?: (doc: API.Document) => void
  onUpload?: (file: File) => void
}) {
  const { list, sessionId, onRemove, onUpload } = props

  return (
    <div className={styles['source']}>
      <div className={styles['source__title']}>Sources</div>

      <div className={styles['source__list']}>
        {list.map((source) => (
          <div className={styles['source__item']} key={source.document_id}>
            <img className={styles['icon']} src={IconFile} />
            <span className={styles['name']} title={source.document_name}>
              {source.document_name}
            </span>

            <Button
              className={styles['source__close']}
              shape="circle"
              size="small"
              variant="text"
              color="default"
              onClick={() => onRemove?.(source)}
            >
              <CloseOutlined />
            </Button>
          </div>
        ))}

        {sessionId ? (
          <Upload
            showUploadList={false}
            maxCount={1}
            accept={ACCEPT.map((e) => `.${e}`).join(',')}
            customRequest={async (options) => {
              const file = options.file as File
              try {
                await api.session.quickParse({ session_id: sessionId, file })
                options.onSuccess?.('')
                onUpload?.(file)
                window.$app.message.success('Upload successful')
              } catch (error: any) {
                options.onError?.(error)
              }
            }}
          >
            <Button
              className={styles['source__add']}
              variant="filled"
              color="primary"
              shape="circle"
              size="small"
            >
              <PlusCircleOutlined />
            </Button>
          </Upload>
        ) : (
          <Button
            className={styles['source__add']}
            variant="filled"
            color="primary"
            shape="circle"
            size="small"
            disabled
          >
            <PlusCircleOutlined />
          </Button>
        )}
      </div>
    </div>
  )
}
