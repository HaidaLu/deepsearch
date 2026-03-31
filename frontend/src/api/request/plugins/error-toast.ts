import { AxiosRequestConfig, AxiosResponse, CanceledError } from 'axios'
import { ResponseError } from '../error'
import { IRequestPlugin } from './plugin'

const NETWORK_ERROR_MAP = {
  // '400': 'Bad Request',
  // '401': 'Unauthorized, please login again',
  // '403': 'Access Denied',
  // '404': 'Request Error, Resource Not Found',
  // '405': 'Method Not Allowed',
  // '408': 'Request Timeout',
  429: 'Too many requests, please try again later',
  // '500': 'Internal Server Error',
  // '501': 'Not Implemented',
  // '502': 'Network Error',
  // '503': 'Service Unavailable',
  // '504': 'Network Timeout',
  // '505': 'HTTP Version Not Supported',
}

export const errorToastPlugin: IRequestPlugin = {
  postinstall(instance) {
    instance.interceptors.response.use(
      (response) => response,
      (error) => {
        const response = error.response as AxiosResponse<any> | undefined
        const config = (response?.config ?? error?.config) as AxiosRequestConfig

        if (config && !config.errorToast) return Promise.reject(error)

        // CanceledError mainly comes from repeat.ts canceling duplicate requests
        // this error should not be shown to the user
        if (error instanceof CanceledError) return Promise.reject(error)

        const status = response?.status ?? ''
        const message =
          error instanceof ResponseError
            ? error.message
            : NETWORK_ERROR_MAP[status as keyof typeof NETWORK_ERROR_MAP] ||
              response?.data?.message ||
              response?.data?.detail ||
              response?.data?.error ||
              error.message ||
              'Request error'

        window.$app.message.error(
          typeof message === 'string' ? message : JSON.stringify(message),
        )

        return Promise.reject(error)
      },
    )
  },
}
