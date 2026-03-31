import * as api from '@/api'
import { Background } from '@/layout/base/background'
import { userActions, userState } from '@/store/user'
import { Button, Flex, Form, Input, Tabs, TabsProps } from 'antd'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSnapshot } from 'valtio'
import styles from './index.module.scss'

const IconUser = (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="rgba(0, 0, 0, 0.45)"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
  >
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
    <circle cx="12" cy="7" r="4"></circle>
  </svg>
)

export default function Login() {
  const user = useSnapshot(userState)
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login')

  const [form] = Form.useForm<{
    username: string
    password: string
    repeatPassword: string
  }>()
  useEffect(() => {
    if (user.username) {
      form.setFieldValue('username', user.username)
    }
  }, [])

  async function login() {
    const { username, password } = form.getFieldsValue()
    const { data } = await api.user.login({ username, password })
    window.$app.message.success('Login successful')
    userActions.setUsername(username)
    userActions.setToken(data.access_token)
    navigate('/')
  }
  async function register() {
    const { username, password } = form.getFieldsValue()
    await api.user.register({ username, password })
    window.$app.message.success('Registration successful, please log in')
    form.setFieldValue('password', '')
    form.setFieldValue('repeatPassword', '')
    setActiveTab('login')
  }

  const tabs: TabsProps['items'] = [
    {
      key: 'login',
      label: 'Login',
      children: (
        <Form form={form} onFinish={login} layout="vertical">
          <div className={styles['login-title']}>Welcome back</div>
          <Form.Item
            label="Email or username"
            name="username"
            rules={[{ required: true, message: 'Please enter email or username' }]}
          >
            <Input
              className={styles['login-input']}
              value={form.getFieldValue('username')}
              onChange={(e) => form.setFieldValue('username', e.target.value)}
              placeholder="Please enter email or username"
              size="large"
              suffix={IconUser}
            />
          </Form.Item>
          <Form.Item
            label="Password"
            name="password"
            rules={[{ required: true, message: 'Please enter password' }]}
          >
            <Input.Password
              className={styles['login-input']}
              value={form.getFieldValue('password')}
              onChange={(e) => {
                form.setFieldValue('password', e.target.value)
                form.setFieldValue('repeatPassword', '')
              }}
              placeholder="Please enter password"
              size="large"
            />
          </Form.Item>

          <Form.Item>
            <Button
              className={styles['login-button']}
              type="primary"
              htmlType="submit"
              size="large"
            >
              Login
            </Button>
          </Form.Item>
        </Form>
      ),
    },
    {
      key: 'register',
      label: 'Register',
      children: (
        <Form form={form} onFinish={register} layout="vertical">
          <div className={styles['login-title']}>Create account</div>
          <Form.Item
            label="Email or username"
            name="username"
            rules={[{ required: true, message: 'Please enter email or username' }]}
          >
            <Input
              className={styles['login-input']}
              value={form.getFieldValue('username')}
              onChange={(e) => form.setFieldValue('username', e.target.value)}
              placeholder="Please enter email or username"
              size="large"
              suffix={IconUser}
            />
          </Form.Item>
          <Form.Item
            label="Password"
            name="password"
            rules={[{ required: true, message: 'Please enter password' }]}
          >
            <Input.Password
              className={styles['login-input']}
              value={form.getFieldValue('password')}
              onChange={(e) => {
                form.setFieldValue('password', e.target.value)
                form.setFieldValue('repeatPassword', '')
              }}
              placeholder="Please enter password"
              size="large"
            />
          </Form.Item>
          <Form.Item
            label="Confirm Password"
            name="repeatPassword"
            rules={[
              { required: true, message: 'Please confirm your password' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (value !== getFieldValue('password')) {
                    return Promise.reject(new Error('Passwords do not match'))
                  }
                  return Promise.resolve()
                },
              }),
            ]}
          >
            <Input.Password
              className={styles['login-input']}
              value={form.getFieldValue('repeatPassword')}
              onChange={(e) =>
                form.setFieldValue('repeatPassword', e.target.value)
              }
              placeholder="Please confirm your password"
              size="large"
            />
          </Form.Item>

          <Form.Item>
            <Button
              className={styles['login-button']}
              type="primary"
              htmlType="submit"
              size="large"
            >
              Register
            </Button>
          </Form.Item>
        </Form>
      ),
    },
  ]

  return (
    <Flex
      className={styles['login-page']}
      justify="center"
      align="center"
      style={{ minHeight: '100vh' }}
    >
      <Background />
      <div className={styles['login-card']}>
        <Tabs
          className={styles['login-tabs']}
          items={tabs}
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as 'login' | 'register')}
          destroyInactiveTabPane
        />
      </div>
    </Flex>
  )
}
