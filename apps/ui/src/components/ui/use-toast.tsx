import * as React from "react";

import {
  Toast,
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastTitle,
  ToastViewport,
} from "../ui/toast";

export type ToastProps = React.ComponentProps<typeof Toast>;

const TOAST_LIMIT = 5;

const toastTimeouts = new Map<string, ReturnType<typeof setTimeout>>();

interface ToastState {
  toasts: ToastProps[];
}

const listeners: ((state: ToastState) => void)[] = [];

let memoryState: ToastState = { toasts: [] };

function dispatch(state: ToastState) {
  memoryState = state;
  listeners.forEach((listener) => listener(state));
}

export function toast({ ...props }: ToastProps) {
  const id = props.id ?? Math.random().toString(36).slice(2, 9);
  const toastWithId: ToastProps = {
    ...props,
    id,
  };
  const update = (state: ToastState): ToastState => {
    const toastIndex = state.toasts.findIndex((toast) => toast.id === id);

    if (toastIndex >= 0) {
      const newToasts = [...state.toasts];
      newToasts[toastIndex] = {
        ...newToasts[toastIndex],
        ...toastWithId,
      };
      return {
        ...state,
        toasts: newToasts,
      };
    }

    return {
      ...state,
      toasts: [
        toastWithId,
        ...state.toasts.slice(0, TOAST_LIMIT - 1),
      ],
    };
  };

  dispatch(update(memoryState));

  if (props.duration !== Infinity) {
    toastTimeouts.set(
      id,
      setTimeout(() => {
        dismiss(id);
      }, props.duration ?? 4000)
    );
  }

  return {
    id,
    dismiss: () => dismiss(id),
  };
}

export function dismiss(toastId?: string) {
  if (toastId) {
    runToastTimeout(toastId);
  } else {
    memoryState.toasts.forEach((toast) => {
      if (toast.id) {
        runToastTimeout(toast.id);
      }
    });
  }
}

function runToastTimeout(toastId: string) {
  if (toastTimeouts.has(toastId)) {
    const timeout = toastTimeouts.get(toastId);
    if (timeout) {
      clearTimeout(timeout);
    }
    toastTimeouts.delete(toastId);
  }

  dispatch({
    ...memoryState,
    toasts: memoryState.toasts.filter(({ id }) => id !== toastId),
  });
}

export function useToast() {
  const [state, setState] = React.useState<ToastState>(memoryState);

  React.useEffect(() => {
    listeners.push(setState);
    return () => {
      const index = listeners.indexOf(setState);
      if (index > -1) {
        listeners.splice(index, 1);
      }
    };
  }, []);

  return {
    ...state,
    toast,
    dismiss,
  };
}

export function Toaster() {
  const { toasts } = useToast();

  return (
    <ToastProvider>
      {toasts.map(function ({ id, ...props }) {
        return (
          <Toast key={id} {...props}>
            <div className="grid gap-1">
              {props.title && <ToastTitle>{props.title}</ToastTitle>}
              {props.description && (
                <ToastDescription>{props.description}</ToastDescription>
              )}
            </div>
            {props.action && <div>{props.action}</div>}
            <ToastClose />
          </Toast>
        );
      })}
      <ToastViewport />
    </ToastProvider>
  );
}
