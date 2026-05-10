/**
 * Tiny dropdown that toggles the active i18n locale. Persists the choice
 * via i18next-browser-languagedetector → localStorage (`tickora.lang`).
 *
 * Drop this in the app header next to the theme toggle.
 */
import { GlobalOutlined } from '@ant-design/icons'
import { Dropdown, Tooltip, Button } from 'antd'
import type { MenuProps } from 'antd'
import { useTranslation } from 'react-i18next'

import { SUPPORTED_LANGUAGES, type SupportedLanguage } from '@/i18n'

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation()

  const items: MenuProps['items'] = SUPPORTED_LANGUAGES.map((code) => ({
    key: code,
    label: t(`language.${code}`),
    onClick: () => {
      void i18n.changeLanguage(code)
    },
  }))

  const active = (i18n.resolvedLanguage ?? 'en') as SupportedLanguage

  return (
    <Tooltip title={t('language.label')}>
      <Dropdown menu={{ items, selectable: true, selectedKeys: [active] }} trigger={['click']}>
        <Button type="text" icon={<GlobalOutlined />}>
          {active.toUpperCase()}
        </Button>
      </Dropdown>
    </Tooltip>
  )
}
