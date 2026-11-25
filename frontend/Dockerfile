# Build the React app, then serve the static files with a tiny static server.
FROM node:20-slim AS build
WORKDIR /app
ARG REACT_APP_BACKEND_URL
ARG REACT_APP_AUTH_MODE=selfhost
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
ENV REACT_APP_AUTH_MODE=$REACT_APP_AUTH_MODE
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile
COPY . .
RUN yarn build

FROM node:20-slim
WORKDIR /app
RUN yarn global add serve
COPY --from=build /app/build ./build
EXPOSE 3000
# -s = single-page app fallback so deep links (/p/:id, refresh) work.
CMD ["serve", "-s", "build", "-l", "3000"]
