import 'axios'

declare module 'axios' {
  export interface AxiosRequestConfig {
    /**
     * Whether to show loading overlay
     * plugins/loading.ts
     */
    loading?: boolean

    /**
     * Whether to show toast on request error
     * plugins/error-toast.ts
     */
    errorToast?: boolean

    /**
     * Cancel duplicate requests
     * plugins/repeat.ts
     */
    cancelRepeat?: boolean
    repeatKey?: string

    /**
     * Unwrap API response data
     * Promotes response.data.data to response.data
     * plugins/service.ts
     */
    unwrap?: boolean
  }

  export interface AxiosResponse<T, D> {
    /**
     * Raw data before unwrapping
     * plugins/service.ts
     */
    _data?: {
      code: number
      msg: string
      data: T
    }
  }
}
