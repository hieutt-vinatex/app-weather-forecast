import { useCallback, useState } from "react";

import { ApiError, sendAbsenceNotificationNow } from "../api/client";

export interface SendAbsenceNotificationState {
  send: (adminToken: string) => Promise<void>;
  isSending: boolean;
  message: string | null;
  isError: boolean;
}

export function useSendAbsenceNotification(): SendAbsenceNotificationState {
  const [isSending, setIsSending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [isError, setIsError] = useState(false);

  const send = useCallback(
    async (adminToken: string) => {
      if (isSending) return;
      setIsSending(true);
      setIsError(false);
      setMessage(null);
      try {
        const response = await sendAbsenceNotificationNow(adminToken.trim());
        setIsError(!response.success);
        setMessage(response.message);
      } catch (error) {
        setIsError(true);
        if (error instanceof ApiError && error.status === 401) {
          setMessage("Khóa quản trị không đúng. Hãy kiểm tra NOTIFICATION_ADMIN_TOKEN.");
        } else if (error instanceof ApiError && error.status === 404) {
          setMessage("API gửi thông báo chưa được bật trên backend.");
        } else {
          setMessage("Không thể gửi thông báo. Hãy kiểm tra backend và thử lại.");
        }
      } finally {
        setIsSending(false);
      }
    },
    [isSending],
  );

  return { send, isSending, message, isError };
}
