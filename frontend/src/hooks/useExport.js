import { useMutation, useQuery } from '@tanstack/react-query';
import { exportData, getExportHistory } from '../api/export';

export const useExportData = () => {
  return useMutation({
    mutationFn: exportData,
    onSuccess: (data) => {
      // Create a download link for the blob
      const url = window.URL.createObjectURL(data.blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', data.filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    }
  });
};

export const useExportHistory = () => {
  return useQuery({
    queryKey: ['exportHistory'],
    queryFn: getExportHistory,
  });
};