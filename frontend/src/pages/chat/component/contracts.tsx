import IconMore from '@/assets/chat/more.svg'
import IconObjectActive from '@/assets/chat/object@active.svg'
import IconSearch from '@/assets/chat/search.svg'
import { PlusCircleOutlined } from '@ant-design/icons'
import { Button, Dropdown, Input, Tooltip } from 'antd'
import { useMemo } from 'react'
import styles from './contracts.module.scss'

function ContractItem(props: { item: API.Document }) {
  const { item } = props

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
      },
    ]
  }, [item])

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

export default function Contracts(props: { list: API.Document[] }) {
  const { list } = props

  return (
    <div className={styles['contracts']}>
      <div className={styles['contracts__search']}>
        <Input
          placeholder="Search documents"
          suffix={<img src={IconSearch} alt="search" />}
        />

        <Button color="default" variant="outlined">
          <PlusCircleOutlined />
          Add
        </Button>
      </div>

      <div className={styles['contracts__title']}>Selected Documents</div>

      <div className={styles['contracts__list']}>
        {list.map((item) => (
          <ContractItem key={item.document_id} item={item} />
        ))}
      </div>
    </div>
  )
}
