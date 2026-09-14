# Static server for the public Gauntlet benchmark results site.
FROM nginx:alpine
COPY default.conf /etc/nginx/conf.d/default.conf
COPY public/ /usr/share/nginx/html/
EXPOSE 80
