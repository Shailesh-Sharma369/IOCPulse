import { axiosClient } from './axiosClient';

export const exportData = async (params) => {
  // params: { source, date_from, date_to, format }
  const queryParams = new URLSearchParams();
  if (params.source && params.source !== 'All') {
    queryParams.append('source_domain', params.source);
  }
  if (params.date_from) {
    queryParams.append('date_from', params.date_from);
  }
  if (params.date_to) {
    queryParams.append('date_to', params.date_to);
  }

  const url = `/api/v1/export/${params.format}?${queryParams.toString()}`;
  const response = await axiosClient.get(url, {
    responseType: 'blob'
  });

  // Extract filename from Content-Disposition header if available
  const contentDisposition = response.headers['content-disposition'];
  let filename = `export_${params.format}_${new Date().toISOString()}.${params.format}`;
  if (contentDisposition) {
    const match = contentDisposition.match(/filename="?(.+)"?/);
    if (match) filename = match[1];
  }

  return { blob: response.data, filename };
};

export const getExportHistory = async () => {
  // Not implemented on backend yet – return empty array
  return [];
};