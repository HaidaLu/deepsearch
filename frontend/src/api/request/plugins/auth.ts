import { router } from '@/router/routes'
import { userActions, userState } from '@/store/user'
import { ResponseError } from '../error'
import { IRequestPlugin } from './plugin'
import { MESSAGE_KEY } from './service'

const AUTH_ERROR_MAP = {
  401: 'Session expired, please log in again',
}

const blackList = ['/login']

export const authPlugin: IRequestPlugin = {
  install(instance) {
    instance.interceptors.request.use((config) => {
      const { token } = userState
      if (token && !config.headers['Authorization']) {
        config.headers['Authorization'] = `Bearer ${token}`
      }
      return config
    })

    instance.interceptors.response.use(
      (response) => response,
      (error) => {
        const response = error.response
        if (!response) return Promise.reject(error)
        const url = response.config.url as string
        if (blackList.includes(url)) return Promise.reject(error)

        const code = response?.status
        const msg = response?.data?.[MESSAGE_KEY]

        let message: string
        switch (code) {
          case 401:
            // token expired
            userActions.setToken('')
            router.navigate('/login')

            message =
              AUTH_ERROR_MAP[code as keyof typeof AUTH_ERROR_MAP] ||
              msg ||
              'Request error'

            return Promise.reject(new ResponseError(message, response))
          case 461:
            // no documents in knowledge base
            message = 'Please upload documents first'
            router.navigate('/repository')

            return Promise.reject(new ResponseError(message, response))
          default:
            return Promise.reject(error)
        }
      },
    )
  },
}
