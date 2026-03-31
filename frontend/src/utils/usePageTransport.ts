import { useMount } from 'ahooks'
import { useState } from 'react'

const tempMap = new Map<PageTransportKey<any>, any>()

// @ts-ignore
export interface PageTransportKey<T> extends Symbol {}

/**
 * Used for data transport between pages.
 * Note: only effective during component initialization.
 */
export function usePageTransport<T>(key: PageTransportKey<T>) {
  const [data, setData] = useState<T | undefined>(() => tempMap.get(key))

  useMount(() => {
    const tempData = tempMap.get(key)
    setData(tempData)
    tempMap.delete(key)
  })

  return {
    data,
    setData,
  }
}

export function setPageTransport<T>(key: PageTransportKey<T>, data: T) {
  tempMap.set(key, data)
}
