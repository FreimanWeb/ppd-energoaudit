import { FrontendRendererArgs } from "@streamlit/component-v2-lib";
import { FC, ReactElement, useCallback, useEffect, useRef, useState } from "react";
import { Calendar, CustomProvider } from "rsuite";
import ruRU from "rsuite/locales/ru_RU";

import "rsuite/dist/rsuite-no-reset.min.css";
import "./telemetry-calendar.css";

export type TelemetryCalendarState = { selected_date: string };

export type TelemetryCalendarData = {
  value: string;
  cellClasses: Record<string, string>;
  minDate: string;
  maxDate: string;
};

type Props = Pick<
  FrontendRendererArgs<TelemetryCalendarState, TelemetryCalendarData>,
  "setStateValue"
> & { data: TelemetryCalendarData };

function parseDate(value: string): Date {
  return new Date(`${value}T00:00:00`);
}

function isoDate(value: Date): string {
  return [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, "0"),
    String(value.getDate()).padStart(2, "0"),
  ].join("-");
}

const TelemetryCalendar: FC<Props> = ({ data, setStateValue }): ReactElement => {
  const [selected, setSelected] = useState(() => parseDate(data.value));
  const previousValue = useRef(data.value);
  useEffect(() => {
    if (data.value !== previousValue.current) {
      previousValue.current = data.value;
      setSelected(parseDate(data.value));
    }
  }, [data.value]);

  const onSelect = useCallback(
    (next: Date | null) => {
      if (!next || !(isoDate(next) in data.cellClasses)) return;
      setSelected(next);
      setStateValue("selected_date", isoDate(next));
    },
    [data.cellClasses, setStateValue],
  );

  const cellClassName = useCallback(
    (day: Date) => {
      const status = data.cellClasses[isoDate(day)];
      return status ? `ppd-telemetry-calendar__${status}` : undefined;
    },
    [data.cellClasses],
  );

  return (
    <CustomProvider locale={ruRU}>
      <Calendar
        value={selected}
        onSelect={onSelect}
        isoWeek
        compact
        cellClassName={cellClassName}
      />
    </CustomProvider>
  );
};

export default TelemetryCalendar;
