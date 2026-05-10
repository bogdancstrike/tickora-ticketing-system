/**
 * Page-scoped product tour built on react-joyride.
 *
 * Pages opt in by rendering `<ProductTour pageKey="tickets" steps={[…]} />`
 * once. The component decides whether to show the tour:
 *   - `localStorage[tour:<pageKey>]` already set → hidden.
 *   - User clicked the help button (we expose `showTour(pageKey)` for that).
 *
 * Steps reference DOM nodes by data-tour-id rather than CSS selectors so a
 * style refactor doesn't silently break the tour.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Joyride, STATUS, type EventData, type Step } from 'react-joyride'
import { theme as antTheme } from 'antd'

const STORAGE_PREFIX = 'tour:'

function isSeen(pageKey: string): boolean {
  try {
    return !!localStorage.getItem(STORAGE_PREFIX + pageKey)
  } catch {
    return true
  }
}

function markSeen(pageKey: string): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + pageKey, '1')
  } catch {
    // ignore — tour will simply replay next visit
  }
}

/** Imperative trigger: useful for a "Show tour" button in the page header. */
export function showTour(pageKey: string): void {
  try {
    localStorage.removeItem(STORAGE_PREFIX + pageKey)
    // Force a re-render of any mounted ProductTour by dispatching a
    // storage event manually (react-joyride listens to its `run` prop, so
    // we use a global event the component listens to).
    window.dispatchEvent(new CustomEvent('tickora:show-tour', { detail: pageKey }))
  } catch {
    // ignore
  }
}

interface ProductTourProps {
  /** Stable identifier — used as the localStorage key. */
  pageKey: string
  /** Steps to walk through. `target` should reference `[data-tour-id="…"]`. */
  steps: Step[]
}

export function ProductTour({ pageKey, steps }: ProductTourProps) {
  const { t } = useTranslation()
  const { token } = antTheme.useToken()
  const [run, setRun] = useState<boolean>(() => !isSeen(pageKey))

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
    if (finished) {
      markSeen(pageKey)
      setRun(false)
    }
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
