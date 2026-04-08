import IconMore from '@/assets/chat/more.svg'
import IconObjectActive from '@/assets/chat/object@active.svg'
import IconSearch from '@/assets/chat/search.svg'
import { PlusCircleOutlined } from '@ant-design/icons'
import { Button, Dropdown, Input, Tooltip } from 'antd'
import { useMemo, useState } from 'react'
import styles from './contracts.module.scss'

function ContractItem(props: { item: API.Document; onRemove?: (doc: API.Document) => void }) {
  const { item, onRemove } = props

  const moreMenu = useMemo(() => {
    return [
      {
        key: 'Read',
        label: 'Read',
      },
      {
        key: 'Suspend',
        label: 'Pause',
      },
      {
        key: 'Remove',
        label: 'Remove',
        onClick: () => onRemove?.(item),
      },
    ]
  }, [item, onRemove])

  return (
    <div className={styles['contracts__item']}>
      <div className={styles['name']} title={item.document_name}>
        {item.document_name}
      </div>
      <div className={styles['actions']}>
        <Tooltip
          classNames={{
            root: styles['contracts-tooltip'],
          }}
          title="Dig"
        >
          <Button color="primary" variant="text" shape="circle" size="small">
            <img src={IconObjectActive} />
          </Button>
        </Tooltip>

        <Dropdown menu={{ items: moreMenu }}>
          <Button color="primary" variant="text" shape="circle" size="small">
            <img src={IconMore} />
          </Button>
        </Dropdown>
      </div>
    </div>
  )
}

export default function Contracts(props: { list: API.Document[]; onRemove?: (doc: API.Document) => void }) {
  const { list, onRemove } = props
  const [search, setSearch] = useState('')

  const filtered = useMemo(
    () => list.filter((d) => d.document_name.toLowerCase().includes(search.toLowerCase())),
    [list, search],
  )

  return (
    <div className={styles['contracts']}>
      <div className={styles['contracts__search']}>
        <Input
          placeholder="Search documents"
          suffix={<img src={IconSearch} alt="search" />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        <Button color="default" variant="outlined">
          <PlusCircleOutlined />
          Add
        </Button>
      </div>

      <div className={styles['contracts__title']}>Selected Documents</div>

      <div className={styles['contracts__list']}>
        {filtered.map((item) => (
          <ContractItem key={item.document_id} item={item} onRemove={onRemove} />
        ))}
      </div>
    </div>
  )
}
