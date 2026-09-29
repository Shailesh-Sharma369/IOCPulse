import { useQuery } from '@tanstack/react-query';
import { getRawArticles, getRawArticleById, getProcessedArticles, getProcessedArticleById } from '../api/articles';

export const useRawArticles = (params) => {
  return useQuery({
    queryKey: ['rawArticles', params],
    queryFn: () => getRawArticles(params),
    keepPreviousData: true,
    staleTime: 0, // Force refetch on mount
    refetchOnMount: true,
  });
};

export const useRawArticle = (id) => {
  return useQuery({
    queryKey: ['rawArticle', id],
    queryFn: () => getRawArticleById(id),
    enabled: !!id,
  });
};

export const useProcessedArticles = (params) => {
  return useQuery({
    queryKey: ['processedArticles', params],
    queryFn: () => getProcessedArticles(params),
    keepPreviousData: true,
    staleTime: 0, // Force refetch on mount
    refetchOnMount: true,
  });
};

export const useProcessedArticle = (id) => {
  return useQuery({
    queryKey: ['processedArticle', id],
    queryFn: () => getProcessedArticleById(id),
    enabled: !!id,
  });
};