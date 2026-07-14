# Nginx reverse proxy with Let's Encrypt-ready volumes
FROM nginx:1.27-alpine
RUN apk add --no-cache certbot certbot-nginx curl bash tini openssl
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx/conf.d/ /etc/nginx/conf.d/
COPY deploy/nginx/certbot-init.sh /usr/local/bin/certbot-init.sh
RUN chmod +x /usr/local/bin/certbot-init.sh
EXPOSE 80 443
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["nginx", "-g", "daemon off;"]
