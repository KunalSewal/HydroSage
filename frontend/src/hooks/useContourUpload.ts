import { useCallback, useRef, useState } from 'react'
import { analyzeContourFile, type CatchmentAnalysis } from '../api/client'

export type ContourUploadStatus = 'idle' | 'uploading' | 'analyzed' | 'error'

export interface ContourUploadState {
  status: ContourUploadStatus
  result: CatchmentAnalysis | null
  errorMessage: string | null
  fileName: string | null
}

const initialState: ContourUploadState = {
  status: 'idle',
  result: null,
  errorMessage: null,
  fileName: null,
}

export function useContourUpload() {
  const [state, setState] = useState<ContourUploadState>(initialState)
  const requestId = useRef(0)

  const upload = useCallback(async (file: File) => {
    const id = ++requestId.current
    setState({ status: 'uploading', result: null, errorMessage: null, fileName: file.name })
    try {
      const result = await analyzeContourFile(file)
      if (id !== requestId.current) return // superseded by a newer upload -- discard
      setState({ status: 'analyzed', result, errorMessage: null, fileName: file.name })
    } catch (error) {
      if (id !== requestId.current) return
      setState({
        status: 'error',
        result: null,
        errorMessage: error instanceof Error ? error.message : 'something went wrong',
        fileName: file.name,
      })
    }
  }, [])

  const reset = useCallback(() => {
    requestId.current += 1 // discard any in-flight upload
    setState(initialState)
  }, [])

  return { state, upload, reset }
}
