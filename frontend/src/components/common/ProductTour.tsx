/**
 * Page-scoped product tour built on react-joyride.
 *
 * The tour is **opt-in**: it never auto-pops on page load. Pages render
 * a `<TourInfoButton pageKey="…" />` next to their refresh control; the
 * matching `<ProductTour pageKey="…" steps={[…]} />` listens for the
 * `tickora:show-tour` event the button fires and starts the walkthrough.
 *
 * Steps reference DOM nodes by `data-tour-id` rather than CSS selectors
 * so a style refactor doesn't silently break the tour.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Joyride, STATUS, type EventData, type Step } from 'react-joyride'
import { Button, Tooltip, theme as antTheme } from 'antd'
import { InfoCircleOutlined } from '@ant-design/icons'


/** Imperative trigger: page header buttons call this to start the tour. */
export function showTour(pageKey: string): void {
  window.dispatchEvent(new CustomEvent('tickora:show-tour', { detail: pageKey }))
}


interface TourInfoButtonProps {
  pageKey: string
  /** Tooltip override; defaults to the i18n `tour.info_button` string. */
  tooltip?: string
}

/** Static info button that pages drop into their toolbar. */
export function TourInfoButton({ pageKey, tooltip }: TourInfoButtonProps) {
  const { t } = useTranslation()
  return (
    <Tooltip title={tooltip ?? t('tour.info_button')}>
      <Button
        type="text"
        icon={<InfoCircleOutlined />}
        onClick={() => showTour(pageKey)}
        aria-label={t('tour.info_button')}
      />
    </Tooltip>
  )
}


interface ProductTourProps {
  /** Stable identifier — matches the `<TourInfoButton pageKey>`. */
  pageKey: string
  /** Steps to walk through. `target` should reference `[data-tour-id="…"]`. */
  steps: Step[]
}

export function ProductTour({ pageKey, steps }: ProductTourProps) {
  const { t } = useTranslation()
  const { token } = antTheme.useToken()
  const [run, setRun] = useState(false)

  useEffect(() => {
    function onShow(e: Event) {
      const detail = (e as CustomEvent<string>).detail
      if (detail === pageKey) setRun(true)
    }
    window.addEventListener('tickora:show-tour', onShow)
    return () => window.removeEventListener('tickora:show-tour', onShow)
  }, [pageKey])

  function onCallback(data: EventData) {
    const finished = ([STATUS.FINISHED, STATUS.SKIPPED] as string[]).includes(data.status as string)
    if (finished) setRun(false)
  }

  return (
    <Joyride
      steps={steps}
      run={run}
      continuous
      showSkipButton
      showProgress
      disableOverlayClose
      callback={onCallback}
      locale={{
        back:  t('tour.buttons.back'),
        close: t('tour.buttons.close'),
        last:  t('tour.buttons.last'),
        next:  t('tour.buttons.next'),
        skip:  t('tour.buttons.skip'),
      }}
      styles={{
        options: {
          primaryColor: token.colorPrimary,
          backgroundColor: token.colorBgContainer,
          textColor: token.colorText,
          zIndex: 2000,
        },
      }}
    />
  )
}
