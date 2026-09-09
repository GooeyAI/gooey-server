import type { ErrorSnackbarProps } from "@gooey-types/error_snackbar_props";
import { useSnackbar } from "notistack";
import { useEffect } from "react";

import type { CustomComponentProps } from "~/components";

export function ErrorSnackbar({
  message,
  snackbar_id,
}: CustomComponentProps & ErrorSnackbarProps) {
  const { closeSnackbar, enqueueSnackbar } = useSnackbar();

  useEffect(() => {
    const snackbarKey = enqueueSnackbar(message, {
      key: snackbar_id,
      persist: true,
      preventDuplicate: true,
      style: {
        maxHeight: "min(40vh, 20rem)",
        overflowWrap: "anywhere",
        overflowY: "auto",
        whiteSpace: "pre-wrap",
      },
      variant: "error",
    });

    return () => closeSnackbar(snackbarKey);
  }, [closeSnackbar, enqueueSnackbar, message, snackbar_id]);

  return null;
}
