const TOKEN_STORAGE_KEY =
  'witty-accounting-access-token'

export function getAccessToken(): string | null {
  return sessionStorage.getItem(
    TOKEN_STORAGE_KEY,
  )
}

export function setAccessToken(
  accessToken: string,
): void {
  sessionStorage.setItem(
    TOKEN_STORAGE_KEY,
    accessToken,
  )
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(
    TOKEN_STORAGE_KEY,
  )
}
