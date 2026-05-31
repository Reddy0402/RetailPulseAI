FROM nginx:alpine

# Remove default Nginx HTML configurations
RUN rm -rf /usr/share/nginx/html/*

# Copy live dashboard and background visualizer layout image
COPY index.html /usr/share/nginx/html/index.html
COPY store_layout.png /usr/share/nginx/html/store_layout.png

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
