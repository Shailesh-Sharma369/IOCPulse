import { axiosClient } from './axiosClient';

export const getRawArticles = async (params) => {
  // params should contain: page, page_size, source_domain, status, date_from, date_to, sort_by, sort_dir
  const response = await axiosClient.get('/api/v1/articles/raw', { params });
  return response.data; // Returns { status, data: [...], pagination: {...} }
};

export const getRawArticleById = async (id) => {
  const response = await axiosClient.get(`/api/v1/articles/raw/${id}`);
  return response.data.data; // Returns the single article object
};

export const getProcessedArticles = async (params) => {
  // params should contain: page, page_size, source_domain, verification_status, date_from, date_to, sort_by, sort_dir
  const response = await axiosClient.get('/api/v1/articles/processed', { params });
  return response.data; // Returns { status, data: [...], pagination: {...} }
};

export const getProcessedArticleById = async (id) => {
  const response = await axiosClient.get(`/api/v1/articles/processed/${id}`);
  return response.data.data;
};