import { axiosClient } from './axiosClient';

export const getSources = async () => {
  const response = await axiosClient.get('/api/v1/sources');
  return response.data.data; // sources uses success_response wrapper
};

export const startIngestionJob = async (payload) => {
  const response = await axiosClient.post('/api/v1/jobs/ingestion/start', payload);
  return response.data; // raw JobResponse object (not wrapped)
};

export const startProcessingJob = async (payload) => {
  const response = await axiosClient.post('/api/v1/jobs/processing/start', payload);
  return response.data; // raw JobResponse object
};

export const getJob = async (jobId) => {
  const response = await axiosClient.get(`/api/v1/jobs/${jobId}`);
  return response.data; // raw JobResponse object
};

export const getJobs = async (limit = 10) => {
  const response = await axiosClient.get(`/api/v1/jobs?limit=${limit}`);
  return response.data; // array of JobResponse objects
};