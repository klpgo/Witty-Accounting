interface PasswordFieldsProps {
  newPassword: string
  confirmPassword: string
  onNewPasswordChange: (
    value: string,
  ) => void
  onConfirmPasswordChange: (
    value: string,
  ) => void
}

function PasswordFields({
  newPassword,
  confirmPassword,
  onNewPasswordChange,
  onConfirmPasswordChange,
}: PasswordFieldsProps) {
  return (
    <div className="form-grid">
      <label className="form-field">
        Neues Passwort
        <input
          type="password"
          value={newPassword}
          required
          minLength={8}
          maxLength={1024}
          autoComplete="new-password"
          onChange={(event) =>
            onNewPasswordChange(
              event.target.value,
            )
          }
        />
      </label>

      <label className="form-field">
        Passwort wiederholen
        <input
          type="password"
          value={confirmPassword}
          required
          minLength={8}
          maxLength={1024}
          autoComplete="new-password"
          onChange={(event) =>
            onConfirmPasswordChange(
              event.target.value,
            )
          }
        />
      </label>
    </div>
  )
}

export default PasswordFields
